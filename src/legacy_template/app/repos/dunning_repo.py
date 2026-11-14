# -*- coding: utf-8 -*-
"""逾期催收案件工单仓储。"""
import sqlite3
from typing import Any, Dict, List


def upsert_dunning_case(conn: sqlite3.Connection, case_data: Dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO dunning_cases (
            id, tenant_id, invoice_id, stage, overdue_days, unpaid_cents, last_notified_at, status, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            stage = excluded.stage,
            overdue_days = excluded.overdue_days,
            unpaid_cents = excluded.unpaid_cents,
            last_notified_at = COALESCE(excluded.last_notified_at, dunning_cases.last_notified_at),
            status = excluded.status,
            updated_at = excluded.updated_at
        """,
        (
            case_data["id"],
            case_data["tenant_id"],
            case_data["invoice_id"],
            case_data["stage"],
            int(case_data["overdue_days"]),
            int(case_data["unpaid_cents"]),
            case_data.get("last_notified_at"),
            case_data.get("status", "OPEN"),
            case_data["updated_at"],
        ),
    )


def list_open_dunning_cases(conn: sqlite3.Connection, limit: int = 100) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT d.*, t.company_name, t.tier_level
        FROM dunning_cases d
        JOIN tenants t ON t.id = d.tenant_id
        WHERE d.status = 'OPEN'
        ORDER BY d.overdue_days DESC, d.unpaid_cents DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def resolve_dunning_for_invoice(conn: sqlite3.Connection, invoice_id: str, updated_at: str) -> int:
    cur = conn.execute(
        "UPDATE dunning_cases SET status = 'RESOLVED', unpaid_cents = 0, updated_at = ? WHERE invoice_id = ? AND status = 'OPEN'",
        (updated_at, invoice_id),
    )
    return cur.rowcount
