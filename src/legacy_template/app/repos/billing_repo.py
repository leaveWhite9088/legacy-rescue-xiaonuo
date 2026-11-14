# -*- coding: utf-8 -*-
"""账单、账单明细行、支付流水与跨期调账单仓储。"""
import sqlite3
from typing import Any, Dict, List, Optional

from app.infra.db import parse_legacy_amount_cents


def serialize_invoice_row(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    d["effective_total_cents"] = parse_legacy_amount_cents(d, "total_cents")
    return d


def get_invoice(conn: sqlite3.Connection, invoice_id: str) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()


def find_cycle_invoice(
    conn: sqlite3.Connection,
    tenant_id: str,
    cycle_start: str,
    cycle_end: str,
) -> Optional[sqlite3.Row]:
    return conn.execute(
        """
        SELECT * FROM invoices
        WHERE tenant_id = ? AND cycle_start = ? AND cycle_end = ? AND status != 'VOID'
        ORDER BY created_at ASC LIMIT 1
        """,
        (tenant_id, cycle_start, cycle_end),
    ).fetchone()


def list_tenant_invoices(conn: sqlite3.Connection, tenant_id: str) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM invoices WHERE tenant_id = ? ORDER BY created_at DESC",
        (tenant_id,),
    ).fetchall()
    return [serialize_invoice_row(r) for r in rows]


def list_period_invoices(conn: sqlite3.Connection, period_key: str, include_void: bool = False) -> List[Dict[str, Any]]:
    if include_void:
        rows = conn.execute(
            "SELECT * FROM invoices WHERE period_key = ? ORDER BY id ASC",
            (period_key,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM invoices WHERE period_key = ? AND status != 'VOID' ORDER BY id ASC",
            (period_key,),
        ).fetchall()
    return [serialize_invoice_row(r) for r in rows]


def list_invoice_lines(conn: sqlite3.Connection, invoice_id: str) -> List[Dict[str, Any]]:
    rows = conn.execute("SELECT * FROM invoice_lines WHERE invoice_id = ? ORDER BY id ASC", (invoice_id,)).fetchall()
    return [dict(r) for r in rows]


def list_invoice_payments(conn: sqlite3.Connection, invoice_id: str) -> List[Dict[str, Any]]:
    rows = conn.execute("SELECT * FROM invoice_payments WHERE invoice_id = ? ORDER BY created_at ASC", (invoice_id,)).fetchall()
    return [dict(r) for r in rows]


def insert_invoice_with_lines(
    conn: sqlite3.Connection,
    inv_data: Dict[str, Any],
    lines: List[Dict[str, Any]],
) -> None:
    conn.execute(
        """
        INSERT INTO invoices (
            id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
            base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents,
            paid_cents, refunded_cents, currency_unit, status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 'CENTS', ?, ?, ?)
        """,
        (
            inv_data["id"],
            inv_data["tenant_id"],
            inv_data["period_key"],
            inv_data["cycle_start"],
            inv_data["cycle_end"],
            inv_data["plan_code"],
            inv_data["base_fee_cents"],
            inv_data["overage_fee_cents"],
            inv_data.get("tax_cents", 0),
            inv_data.get("late_fee_cents", 0),
            inv_data["total_cents"],
            inv_data.get("status", "OPEN"),
            inv_data["created_at"],
            inv_data["updated_at"],
        ),
    )
    for ln in lines:
        conn.execute(
            """
            INSERT INTO invoice_lines (invoice_id, line_type, description, quantity, unit_price_cents, amount_cents)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                inv_data["id"],
                ln["line_type"],
                ln["description"],
                ln.get("quantity", 1),
                ln.get("unit_price_cents", ln["amount_cents"]),
                ln["amount_cents"],
            ),
        )


def insert_billing_adjustment(
    conn: sqlite3.Connection,
    adj_id: str,
    tenant_id: str,
    ref_invoice_id: str,
    target_period_key: str,
    applied_period_key: str,
    adjustment_type: str,
    delta_cents: int,
    reason: str,
    created_at: str,
    status: str = "PENDING",
) -> None:
    conn.execute(
        """
        INSERT INTO billing_adjustments (
            id, tenant_id, ref_invoice_id, target_period_key, applied_period_key,
            adjustment_type, delta_cents, reason, status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            adj_id,
            tenant_id,
            ref_invoice_id,
            target_period_key,
            applied_period_key,
            adjustment_type,
            int(delta_cents),
            reason,
            status,
            created_at,
        ),
    )
