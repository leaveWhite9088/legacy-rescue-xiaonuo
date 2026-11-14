# -*- coding: utf-8 -*-
"""客户账单争议工单聚合与证据卷宗生成引擎。"""
import sqlite3
from typing import Any, Dict

from app.domain.pricing import calculate_cycle_bill
from app.infra.config import TAX_PROFILES
from app.policies.period_lock_policy import inspect_period_mutability


def build_invoice_dispute_dossier(conn: sqlite3.Connection, invoice_id: str) -> Dict[str, Any]:
    inv = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
    if not inv:
        raise LookupError(f"Invoice not found: {invoice_id}")

    tenant = conn.execute("SELECT * FROM tenants WHERE id = ?", (inv["tenant_id"],)).fetchone()
    period_lock = inspect_period_mutability(conn, inv["period_key"])
    changes = conn.execute(
        "SELECT * FROM plan_change_history WHERE tenant_id = ? ORDER BY effective_at ASC",
        (inv["tenant_id"],),
    ).fetchall()
    segments = conn.execute(
        "SELECT plan_code, total_quantity, updated_at FROM usage_summaries WHERE tenant_id = ? AND period_key = ? ORDER BY id ASC",
        (inv["tenant_id"], inv["period_key"]),
    ).fetchall()
    payments = conn.execute(
        "SELECT * FROM invoice_payments WHERE invoice_id = ? ORDER BY created_at ASC",
        (invoice_id,),
    ).fetchall()
    dunning = conn.execute(
        "SELECT id, stage, overdue_days, unpaid_cents, status FROM dunning_cases WHERE invoice_id = ? ORDER BY updated_at DESC LIMIT 1",
        (invoice_id,),
    ).fetchone()
    fapiao = conn.execute(
        "SELECT id, fapiao_type, gross_amount_cents, status FROM fapiao_requests WHERE invoice_id = ? ORDER BY created_at DESC LIMIT 1",
        (invoice_id,),
    ).fetchone()

    live_recalc = calculate_cycle_bill(conn, inv["tenant_id"], inv["period_key"], inv["plan_code"])
    tax_code = tenant["tax_profile_code"] if tenant else "CN_VAT_6_INCLUSIVE"
    tp = TAX_PROFILES.get(tax_code, TAX_PROFILES["CN_VAT_6_INCLUSIVE"])

    sla_priority = "P1_ENTERPRISE" if int(inv["total_cents"] or 0) >= 100_000 else "P2_STANDARD"
    return {
        "invoice_id": invoice_id,
        "tenant_id": inv["tenant_id"],
        "company_name": tenant["company_name"] if tenant else "",
        "period_key": inv["period_key"],
        "invoice_status": inv["status"],
        "dispute_reason": inv["dispute_reason"],
        "sla_priority": sla_priority,
        "period_lock_policy": period_lock,
        "tax_profile": tp,
        "plan_change_count": len(changes),
        "usage_summary_rows": [dict(s) for s in segments],
        "billed_total_cents": int(inv["total_cents"] or 0),
        "engine_recalculated_total_cents": int(live_recalc["total_cents"]),
        "payment_records": [dict(p) for p in payments],
        "dunning_snapshot": dict(dunning) if dunning else None,
        "fapiao_snapshot": dict(fapiao) if fapiao else None,
    }
