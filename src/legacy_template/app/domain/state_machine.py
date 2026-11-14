# -*- coding: utf-8 -*-
"""订阅与账单状态机约束。"""
import sqlite3
from typing import Iterable

ALLOWED_INVOICE_TRANSITIONS = {
    "OPEN": {"PENDING_SETTLE", "PAID", "VOID"},
    "PENDING_SETTLE": {"OPEN", "PAID", "VOID"},
    "PAID": {"REFUNDED"},
    "REFUNDED": set(),
    "VOID": set(),
}


def can_transition_invoice(current_status: str, target_status: str) -> bool:
    return target_status in ALLOWED_INVOICE_TRANSITIONS.get(current_status, set())


def atomic_transition_invoice(
    conn: sqlite3.Connection,
    invoice_id: str,
    from_statuses: Iterable[str],
    to_status: str,
    updated_at: str,
) -> bool:
    allowed = tuple(from_statuses)
    placeholders = ",".join("?" for _ in allowed)
    cur = conn.execute(
        f"UPDATE invoices SET status = ?, updated_at = ? WHERE id = ? AND status IN ({placeholders})",
        (to_status, updated_at, invoice_id, *allowed),
    )
    return cur.rowcount == 1
