# -*- coding: utf-8 -*-
"""财务大额调账、大额退费与授信变更双签审批单仓储。"""
import sqlite3
from typing import Any, Dict, List, Optional


def create_approval_ticket(conn: sqlite3.Connection, ticket: Dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO approval_tickets (
            id, ticket_type, tenant_id, ref_object_id, amount_cents, requested_by,
            first_approver, second_approver, required_approvals, status, reason, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?, 'PENDING', ?, ?, ?)
        """,
        (
            ticket["id"],
            ticket["ticket_type"],
            ticket["tenant_id"],
            ticket["ref_object_id"],
            int(ticket["amount_cents"]),
            ticket["requested_by"],
            int(ticket.get("required_approvals", 1)),
            ticket.get("reason", ""),
            ticket["created_at"],
            ticket["updated_at"],
        ),
    )


def get_approval_ticket(conn: sqlite3.Connection, ticket_id: str) -> Optional[Dict[str, Any]]:
    row = conn.execute("SELECT * FROM approval_tickets WHERE id = ?", (ticket_id,)).fetchone()
    return dict(row) if row else None


def list_approval_tickets(conn: sqlite3.Connection, status: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    if status:
        rows = conn.execute(
            "SELECT * FROM approval_tickets WHERE status = ? ORDER BY created_at DESC LIMIT ?",
            (status, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM approval_tickets ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]
