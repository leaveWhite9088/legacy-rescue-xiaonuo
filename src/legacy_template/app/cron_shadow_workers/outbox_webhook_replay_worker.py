# -*- coding: utf-8 -*-
"""Webhook Outbox 指数退避重试计划计算器与签名回放检验器。"""
import sqlite3
from typing import Any, Dict, List


BACKOFF_SCHEDULE_SECONDS = (0, 60, 300, 1800, 7200)


def compute_next_webhook_backoff_sec(attempts: int) -> int:
    idx = max(0, min(int(attempts), len(BACKOFF_SCHEDULE_SECONDS) - 1))
    return BACKOFF_SCHEDULE_SECONDS[idx]


def inspect_failed_webhook_outbox(conn: sqlite3.Connection, limit: int = 50) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, tenant_id, event_type, delivery_status, attempts, created_at
        FROM webhook_outbox
        WHERE delivery_status != 'DELIVERED'
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [
        {
            **dict(r),
            "next_retry_delay_sec": compute_next_webhook_backoff_sec(int(r["attempts"] or 0)),
        }
        for r in rows
    ]
