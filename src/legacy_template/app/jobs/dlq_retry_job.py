# -*- coding: utf-8 -*-
"""死信重试任务：扫描 settlement_dlq 中待重试的失败结算单并重新尝试扣款。"""
from datetime import datetime, timezone
import sqlite3
from typing import Any, Dict

from app.domain.ledger import pay_invoice_from_wallet
from app.infra.logger import get_logger

log = get_logger("yunce.jobs.dlq")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def retry_pending_dlq(conn: sqlite3.Connection, max_retries: int = 3) -> Dict[str, Any]:
    rows = conn.execute(
        "SELECT * FROM settlement_dlq WHERE status = 'PENDING' AND retry_count < ? ORDER BY id ASC",
        (max_retries,),
    ).fetchall()
    recovered = 0
    still_failing = 0
    now = _now_iso()

    for item in rows:
        inv_id = item["invoice_id"]
        try:
            pay_invoice_from_wallet(conn, inv_id, item["tenant_id"], idempotency_key=f"dlq:{inv_id}:{item['retry_count'] + 1}")
            conn.execute(
                "UPDATE settlement_dlq SET status = 'RESOLVED', updated_at = ? WHERE id = ?",
                (now, item["id"]),
            )
            recovered += 1
        except Exception as exc:
            new_cnt = int(item["retry_count"]) + 1
            new_status = "DEAD" if new_cnt >= max_retries else "PENDING"
            conn.execute(
                "UPDATE settlement_dlq SET retry_count = ?, error_msg = ?, status = ?, updated_at = ? WHERE id = ?",
                (new_cnt, str(exc), new_status, now, item["id"]),
            )
            log.info("dlq_retry: inv=%s retry=%d failed=%s", inv_id, new_cnt, exc)
            still_failing += 1

    return {"recovered": recovered, "still_failing": still_failing}
