# -*- coding: utf-8 -*-
"""账单查询、支付、争议提交与后台重算/退款门面层。"""
import sqlite3
from typing import Any, Dict, Optional

from app.services.billing_service import (
    admin_recalculate_invoice,
    admin_refund_invoice,
    get_invoice_full_detail,
    get_tenant_invoice_list,
    pay_tenant_invoice,
    submit_invoice_dispute,
)


def facade_list_tenant_invoices(conn: sqlite3.Connection, tenant_id: str) -> Dict[str, Any]:
    return get_tenant_invoice_list(conn, tenant_id)


def facade_get_invoice_detail(conn: sqlite3.Connection, requester_tenant_id: str, invoice_id: str) -> Dict[str, Any]:
    return get_invoice_full_detail(conn, requester_tenant_id, invoice_id)


def facade_pay_invoice(
    conn: sqlite3.Connection,
    tenant_id: str,
    invoice_id: str,
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    return pay_tenant_invoice(conn, tenant_id, invoice_id, idempotency_key=idempotency_key)


def facade_dispute_invoice(
    conn: sqlite3.Connection,
    requester_tenant_id: str,
    invoice_id: str,
    reason: str,
) -> Dict[str, Any]:
    return submit_invoice_dispute(conn, requester_tenant_id, invoice_id, reason)


def facade_admin_refund(conn: sqlite3.Connection, invoice_id: str, refund_cents: int, reason: str) -> Dict[str, Any]:
    return admin_refund_invoice(conn, invoice_id, refund_cents, reason=reason)


def facade_admin_recalculate(conn: sqlite3.Connection, invoice_id: str) -> Dict[str, Any]:
    return admin_recalculate_invoice(conn, invoice_id)
