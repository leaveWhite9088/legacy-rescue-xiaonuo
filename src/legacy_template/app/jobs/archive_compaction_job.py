# -*- coding: utf-8 -*-
"""Webhook 历史已投递消息归档清理任务。"""
import sqlite3
from typing import Any, Dict


def compact_delivered_webhooks(conn: sqlite3.Connection, keep_latest: int = 500) -> Dict[str, Any]:
    row = conn.execute("SELECT COUNT(*) AS cnt FROM webhook_outbox WHERE delivery_status = 'DELIVERED'").fetchone()
    delivered_cnt = int(row["cnt"] or 0) if row else 0
    if delivered_cnt <= keep_latest:
        return {"pruned_webhooks": 0, "remaining_delivered": delivered_cnt}
    to_prune = delivered_cnt - keep_latest
    conn.execute(
        """
        DELETE FROM webhook_outbox
        WHERE id IN (
            SELECT id FROM webhook_outbox
            WHERE delivery_status = 'DELIVERED'
            ORDER BY created_at ASC
            LIMIT ?
        )
        """,
        (to_prune,),
    )
    return {"pruned_webhooks": to_prune, "remaining_delivered": keep_latest}
