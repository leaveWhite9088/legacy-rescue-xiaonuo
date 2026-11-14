# -*- coding: utf-8 -*-
"""账期关账、总账生成、对账核验与账单重算引擎。"""
from datetime import datetime, timezone
import sqlite3
import uuid
from typing import Any, Dict

from app.domain.gl_exporter import generate_gl_entries_for_period
from app.domain.pricing import calculate_cycle_bill
from app.infra.db import parse_legacy_amount_cents
from app.repos.billing_repo import get_invoice


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_period_status(conn: sqlite3.Connection, period_key: str) -> str:
    row = conn.execute(
        "SELECT status FROM accounting_periods WHERE period_key = ?",
        (period_key,),
    ).fetchone()
    return row["status"] if row else "OPEN"


def close_accounting_period(
    conn: sqlite3.Connection,
    period_key: str,
    actor: str = "admin",
) -> Dict[str, Any]:
    status = get_period_status(conn, period_key)
    if status == "CLOSED":
        raise ValueError(f"账期 {period_key} 已经关账")

    rows = conn.execute(
        "SELECT * FROM invoices WHERE period_key = ? AND status != 'VOID'",
        (period_key,),
    ).fetchall()
    archived_total = sum(parse_legacy_amount_cents(dict(r), "total_cents") for r in rows)
    now = _now_iso()

    conn.execute(
        """
        INSERT INTO accounting_periods (period_key, status, closed_at, closed_by, archived_total_cents)
        VALUES (?, 'CLOSED', ?, ?, ?)
        ON CONFLICT(period_key) DO UPDATE SET
            status = 'CLOSED',
            closed_at = excluded.closed_at,
            closed_by = excluded.closed_by,
            archived_total_cents = excluded.archived_total_cents
        """,
        (period_key, now, actor, archived_total),
    )
    gl_summary = generate_gl_entries_for_period(conn, period_key)
    conn.execute(
        """
        INSERT INTO audit_logs (actor, action, target_id, detail, created_at)
        VALUES (?, 'CLOSE_PERIOD', ?, ?, ?)
        """,
        (actor, period_key, f"archived_total_cents={archived_total}, gl_entries={gl_summary['entry_count']}", now),
    )
    return {
        "period_key": period_key,
        "status": "CLOSED",
        "archived_total_cents": archived_total,
        "gl_balanced": gl_summary["balanced"],
        "closed_at": now,
    }


def recalculate_invoice_for_period(
    conn: sqlite3.Connection,
    invoice_id: str,
    actor: str = "system",
) -> Dict[str, Any]:
    """根据当期最新汇总重算账单各项金额。"""
    inv = get_invoice(conn, invoice_id)
    if not inv:
        raise ValueError(f"Invoice not found: {invoice_id}")

    bill = calculate_cycle_bill(conn, inv["tenant_id"], inv["period_key"], inv["plan_code"])
    new_total = bill["total_cents"] + int(inv["late_fee_cents"])
    now = _now_iso()

    conn.execute(
        """
        UPDATE invoices
        SET base_fee_cents = ?, overage_fee_cents = ?, tax_cents = ?, total_cents = ?, updated_at = ?
        WHERE id = ?
        """,
        (bill["base_fee_cents"], bill["overage_fee_cents"], bill["tax_cents"], new_total, now, invoice_id),
    )
    conn.execute(
        "INSERT INTO audit_logs (actor, action, target_id, detail, created_at) VALUES (?, 'RECALC_INVOICE', ?, ?, ?)",
        (actor, invoice_id, f"period={inv['period_key']}, new_total={new_total}", now),
    )
    return {
        "invoice_id": invoice_id,
        "period_key": inv["period_key"],
        "mode": "DIRECT_OVERWRITE",
        "new_total_cents": new_total,
    }


def build_reconciliation_report(conn: sqlite3.Connection, period_key: str) -> Dict[str, Any]:
    period = conn.execute(
        "SELECT * FROM accounting_periods WHERE period_key = ?",
        (period_key,),
    ).fetchone()
    invoices = conn.execute(
        "SELECT * FROM invoices WHERE period_key = ? AND status != 'VOID'",
        (period_key,),
    ).fetchall()
    computed_total = sum(parse_legacy_amount_cents(dict(r), "total_cents") for r in invoices)
    tax_total = sum(int(r["tax_cents"] or 0) for r in invoices)
    paid_total = sum(int(r["paid_cents"]) for r in invoices)
    refunded_total = sum(int(r["refunded_cents"]) for r in invoices)

    adjustments = conn.execute(
        "SELECT * FROM billing_adjustments WHERE target_period_key = ? OR applied_period_key = ?",
        (period_key, period_key),
    ).fetchall()

    return {
        "period_key": period_key,
        "status": period["status"] if period else "OPEN",
        "archived_total_cents": period["archived_total_cents"] if period else None,
        "computed_invoice_total_cents": computed_total,
        "tax_total_cents": tax_total,
        "paid_total_cents": paid_total,
        "refunded_total_cents": refunded_total,
        "invoice_count": len(invoices),
        "discrepancy_vs_archive_cents": (
            None if (not period or period["archived_total_cents"] is None)
            else computed_total - int(period["archived_total_cents"])
        ),
        "adjustments": [dict(a) for a in adjustments],
    }
