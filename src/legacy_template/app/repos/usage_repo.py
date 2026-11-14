# -*- coding: utf-8 -*-
"""计量事件缓冲表与月度分段汇总表访问仓储。"""
import sqlite3
from typing import Any, Dict, List


def insert_usage_event(
    conn: sqlite3.Connection,
    event_id: str,
    tenant_id: str,
    quantity: int,
    occurred_at: str,
    period_key: str,
    plan_code_at_event: str | None = None,
    metric_code: str = "API_CALLS",
) -> None:
    conn.execute(
        """
        INSERT INTO usage_events (id, tenant_id, metric_code, quantity, plan_code_at_event, occurred_at, period_key, flushed)
        VALUES (?, ?, ?, ?, ?, ?, ?, 0)
        """,
        (event_id, tenant_id, metric_code, quantity, plan_code_at_event, occurred_at, period_key),
    )


def get_period_usage_breakdown(conn: sqlite3.Connection, tenant_id: str, period_key: str) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT plan_code, total_quantity FROM usage_summaries WHERE tenant_id = ? AND period_key = ?",
        (tenant_id, period_key),
    ).fetchall()
    return [dict(r) for r in rows]


def get_unflushed_quantity(conn: sqlite3.Connection, tenant_id: str, period_key: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(quantity), 0) AS qty FROM usage_events WHERE tenant_id = ? AND period_key = ? AND flushed = 0",
        (tenant_id, period_key),
    ).fetchone()
    return int(row["qty"]) if row else 0
