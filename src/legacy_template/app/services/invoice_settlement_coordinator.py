# -*- coding: utf-8 -*-
"""账单钱包扣划编排与结算预览协同服务。"""
import sqlite3
from typing import Any, Dict
from app.domain.ledger import pay_invoice_from_wallet


def execute_portal_invoice_payment(
    conn: sqlite3.Connection,
    tenant_id: str,
    invoice_id: str,
    idempotency_key: str | None = None,
) -> Dict[str, Any]:
    if idempotency_key:
        hit = conn.execute(
            "SELECT * FROM invoice_payments WHERE idempotency_key = ? LIMIT 1",
            (idempotency_key,),
        ).fetchone()
        if hit:
            return {"invoice_id": hit["invoice_id"], "idempotent_replay": True}
    return pay_invoice_from_wallet(conn, tenant_id, invoice_id, idempotency_key=idempotency_key)


def build_portal_settlement_preview(conn: sqlite3.Connection, tenant_id: str, invoice_id: str) -> Dict[str, Any]:
    inv = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
    if not inv:
        raise LookupError("Invoice not found")
    w = conn.execute("SELECT * FROM wallets WHERE tenant_id = ?", (tenant_id,)).fetchone()
    due = max(0, int(inv["total_cents"]))
    promo = min(due, max(0, int(w["promo_balance_cents"]) if w else 0))
    return {"invoice_id": invoice_id, "due_cents": due, "promo_deduct_cents": promo, "cash_deduct_cents": due - promo}
