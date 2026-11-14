# -*- coding: utf-8 -*-
"""订阅主记录与套餐变更历史仓储。"""
import sqlite3
from typing import Any, Dict, List, Optional


def get_latest_subscription(conn: sqlite3.Connection, tenant_id: str) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM subscriptions WHERE tenant_id = ? ORDER BY updated_at DESC LIMIT 1",
        (tenant_id,),
    ).fetchone()


def list_due_subscriptions(conn: sqlite3.Connection, as_of_iso: str) -> List[sqlite3.Row]:
    return conn.execute(
        """
        SELECT s.*, t.status AS tenant_status
        FROM subscriptions s
        JOIN tenants t ON t.id = s.tenant_id
        WHERE s.status IN ('ACTIVE', 'ACTIVE_LEGACY')
          AND s.auto_renew = 1
          AND s.next_billing_at <= ?
        ORDER BY s.next_billing_at ASC
        """,
        (as_of_iso,),
    ).fetchall()


def record_plan_change(
    conn: sqlite3.Connection,
    subscription_id: str,
    tenant_id: str,
    old_plan: str,
    new_plan: str,
    effective_at: str,
    proration_cents: int,
    reason: str = "",
) -> None:
    conn.execute(
        """
        INSERT INTO plan_change_history
        (subscription_id, tenant_id, old_plan_code, new_plan_code, effective_at, proration_cents, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (subscription_id, tenant_id, old_plan, new_plan, effective_at, proration_cents, reason),
    )


def list_plan_changes(conn: sqlite3.Connection, tenant_id: str) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM plan_change_history WHERE tenant_id = ? ORDER BY effective_at ASC",
        (tenant_id,),
    ).fetchall()
    return [dict(r) for r in rows]
