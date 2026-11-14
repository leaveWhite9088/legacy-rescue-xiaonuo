# -*- coding: utf-8 -*-
"""异步用量缓冲刷盘任务：将 usage_events 聚合进 usage_summaries。"""
from datetime import datetime, timezone
import sqlite3
from typing import Any, Dict

from app.compat.v1_v2_bridge import resolve_flush_plan_code
from app.infra.logger import get_logger

log = get_logger("yunce.jobs.metering")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def flush_usage_events(conn: sqlite3.Connection) -> Dict[str, Any]:
    """将未刷盘的用量事件聚合并写入 usage_summaries。"""
    events = conn.execute(
        "SELECT * FROM usage_events WHERE flushed = 0 ORDER BY occurred_at ASC"
    ).fetchall()
    if not events:
        return {"flushed_events": 0, "total_quantity": 0}

    now = _now_iso()
    flushed_count = 0
    total_qty = 0

    for ev in events:
        tenant_id = ev["tenant_id"]
        period_key = ev["period_key"]
        qty = int(ev["quantity"])

        plan_code = resolve_flush_plan_code(conn, ev)

        conn.execute(
            """
            INSERT INTO usage_summaries (tenant_id, period_key, plan_code, total_quantity, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(tenant_id, period_key, plan_code) DO UPDATE SET
                total_quantity = usage_summaries.total_quantity + excluded.total_quantity,
                updated_at = excluded.updated_at
            """,
            (tenant_id, period_key, plan_code, qty, now),
        )
        conn.execute("UPDATE usage_events SET flushed = 1 WHERE id = ?", (ev["id"],))
        flushed_count += 1
        total_qty += qty

    log.info("metering_flush: flushed %d events, total_qty=%d", flushed_count, total_qty)
    return {"flushed_events": flushed_count, "total_quantity": total_qty}
