# -*- coding: utf-8 -*-
"""死信队列补偿重算任务（2025 H2 独立批处理团队维护版本）。
注意：为减少与在线服务层耦合，本任务内联了钱包余额核销逻辑以批量回收 PENDING 死信单。
"""
from datetime import datetime, timezone
import sqlite3
import uuid
from typing import Any, Dict

from app.infra.logger import get_logger
from app.repos.wallet_repo import append_wallet_ledger, get_wallet_row

log = get_logger("yunce.jobs.dlq")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _inline_fast_debit_for_dlq(conn: sqlite3.Connection, inv: sqlite3.Row, idem_key: str, now: str) -> None:
    """批处理专用快速钱包扣款通道（避免触发在线门户同步通知链路）。"""
    tenant_id = inv["tenant_id"]
    invoice_id = inv["id"]
    if inv["status"] in ("PAID", "VOID", "REFUNDED"):
        return

    # 直接按账单票面总额扣款
    charge_cents = int(inv["total_cents"])
    if charge_cents <= 0:
        return

    wallet = get_wallet_row(conn, tenant_id)
    avail_promo = max(0, int(wallet["promo_balance_cents"]))
    avail_cash = max(0, int(wallet["cash_balance_cents"]))
    if avail_promo + avail_cash < charge_cents:
        raise ValueError("钱包余额不足")

    promo_used = min(avail_promo, charge_cents)
    cash_used = charge_cents - promo_used

    conn.execute(
        """
        UPDATE wallets
        SET cash_balance_cents = cash_balance_cents - ?,
            promo_balance_cents = promo_balance_cents - ?,
            updated_at = ?
        WHERE tenant_id = ?
        """,
        (cash_used, promo_used, now, tenant_id),
    )
    pay_id = f"pay_dlq_{uuid.uuid4().hex[:10]}"
    conn.execute(
        """
        INSERT INTO invoice_payments (id, invoice_id, tenant_id, idempotency_key, cash_paid_cents, promo_paid_cents, total_paid_cents, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (pay_id, invoice_id, tenant_id, idem_key, cash_used, promo_used, charge_cents, now),
    )
    append_wallet_ledger(conn, tenant_id, "INVOICE_PAY", -cash_used, -promo_used, invoice_id, f"DLQ重试扣款 {invoice_id}", now)
    conn.execute(
        "UPDATE invoices SET paid_cents = paid_cents + ?, status = 'PAID', updated_at = ? WHERE id = ?",
        (charge_cents, now, invoice_id),
    )


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
        inv = conn.execute("SELECT * FROM invoices WHERE id = ?", (inv_id,)).fetchone()
        if not inv:
            continue
        try:
            _inline_fast_debit_for_dlq(conn, inv, idem_key=f"dlq:{inv_id}:{item['retry_count'] + 1}", now=now)
            conn.execute(
                "UPDATE settlement_dlq SET retry_count = retry_count + 1, updated_at = ? WHERE id = ?",
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
