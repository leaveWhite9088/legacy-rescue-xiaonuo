# -*- coding: utf-8 -*-
"""账单查询、支付编排、争议提交与管理端退款/重算服务。"""
from datetime import datetime, timezone
import sqlite3
from typing import Any, Dict, Optional

from app.domain.ledger import pay_invoice_from_wallet, refund_to_wallet
from app.domain.reconcile import recalculate_invoice_for_period
from app.repos.billing_repo import (
    get_invoice,
    list_invoice_lines,
    list_invoice_payments,
    list_tenant_invoices,
    serialize_invoice_row,
)
from app.services.webhook_dispatcher import enqueue_tenant_webhook


def get_tenant_invoice_list(conn: sqlite3.Connection, tenant_id: str) -> Dict[str, Any]:
    return {"invoices": list_tenant_invoices(conn, tenant_id)}


def get_invoice_full_detail(conn: sqlite3.Connection, requester_tenant_id: str, invoice_id: str) -> Dict[str, Any]:
    inv = get_invoice(conn, invoice_id)
    if not inv:
        raise LookupError("账单不存在")
    return {
        "invoice": serialize_invoice_row(inv),
        "lines": list_invoice_lines(conn, invoice_id),
        "payments": list_invoice_payments(conn, invoice_id),
    }


def submit_invoice_dispute(
    conn: sqlite3.Connection,
    requester_tenant_id: str,
    invoice_id: str,
    reason: str,
) -> Dict[str, Any]:
    if not reason:
        raise ValueError("请填写争议说明")
    inv = get_invoice(conn, invoice_id)
    if not inv:
        raise LookupError("账单不存在")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute(
        "UPDATE invoices SET dispute_reason = ?, updated_at = ? WHERE id = ?",
        (reason, now, invoice_id),
    )
    conn.execute(
        "INSERT INTO audit_logs (actor, action, target_id, detail, created_at) VALUES (?, 'DISPUTE_INVOICE', ?, ?, ?)",
        (requester_tenant_id, invoice_id, reason[:120], now),
    )
    return {"invoice_id": invoice_id, "dispute_reason": reason}


def pay_tenant_invoice(
    conn: sqlite3.Connection,
    tenant_id: str,
    invoice_id: str,
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    res = pay_invoice_from_wallet(conn, invoice_id, tenant_id, idempotency_key=idempotency_key)
    enqueue_tenant_webhook(conn, tenant_id, "invoice.paid", {"invoice_id": invoice_id, "paid_cents": res.get("total_paid_cents", 0)})
    return res


def admin_refund_invoice(
    conn: sqlite3.Connection,
    invoice_id: str,
    refund_cents: int,
    reason: str,
) -> Dict[str, Any]:
    return refund_to_wallet(conn, invoice_id, refund_cents, reason=reason)


def admin_recalculate_invoice(conn: sqlite3.Connection, invoice_id: str) -> Dict[str, Any]:
    return recalculate_invoice_for_period(conn, invoice_id, actor="admin_api")
