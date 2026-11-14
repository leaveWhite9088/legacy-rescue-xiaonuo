# -*- coding: utf-8 -*-
"""金税四期数电发票（增值税专用发票 / 普通发票 / 红字信息表冲销）编排服务。"""
from datetime import datetime, timezone
import math
import sqlite3
import uuid
from typing import Any, Dict, List

from app.infra.config import FAPIAO_SINGLE_SHEET_MAX_CENTS, FEATURE_FLAGS, TAX_PROFILES
from app.infra.db import parse_legacy_amount_cents
from app.repos.billing_repo import get_invoice
from app.repos.fapiao_repo import (
    find_active_fapiao_for_invoice,
    get_fapiao_by_id,
    insert_fapiao_request,
    list_tenant_fapiaos,
)
from app.repos.tenant_repo import get_tenant_by_id


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def request_vat_fapiao_for_invoice(
    conn: sqlite3.Connection,
    tenant_id: str,
    invoice_id: str,
    buyer_tax_id: str,
    fapiao_type: str = "VAT_SPECIAL_E",
) -> Dict[str, Any]:
    """针对已实付账单申请开具数电增值税发票（自动扣除赠送金抵扣额，仅对现金实付含税额开票）。"""
    tax_no = (buyer_tax_id or "").strip().upper()
    if len(tax_no) < 15 or len(tax_no) > 20:
        raise ValueError("纳税人识别号（统一社会信用代码）长度须为 15~20 位")

    tenant = get_tenant_by_id(conn, tenant_id)
    if not tenant:
        raise LookupError("租户不存在")

    tax_profile = TAX_PROFILES.get(tenant.get("tax_profile_code", "CN_VAT_6_INCLUSIVE"), TAX_PROFILES["CN_VAT_6_INCLUSIVE"])
    if not tax_profile.get("fapiao_eligible", True):
        raise ValueError(f"当前税务档案 {tax_profile['code']} 属于境外税制，不支持开具中国增值税发票")

    inv = get_invoice(conn, invoice_id)
    if not inv:
        raise LookupError("账单不存在")
    if inv["tenant_id"] != tenant_id:
        raise PermissionError("无权为其他租户账单申请开票")
    if inv["status"] != "PAID":
        raise ValueError("仅已结清（PAID）状态的账单支持申请开票")

    existing = find_active_fapiao_for_invoice(conn, invoice_id)
    if existing:
        return existing

    # 依据税法合规要求：运营赠送金视同商业折扣，仅按实际现金支付净额（已扣退款）开票
    pay_row = conn.execute(
        "SELECT COALESCE(SUM(cash_paid_cents), 0) AS cash_paid FROM invoice_payments WHERE invoice_id = ?",
        (invoice_id,),
    ).fetchone()
    cash_paid = int(pay_row["cash_paid"] or 0) if pay_row else parse_legacy_amount_cents(dict(inv), "paid_cents")
    net_cash_invoiceable = max(0, cash_paid - int(inv["refunded_cents"] or 0))
    if net_cash_invoiceable <= 0:
        raise ValueError("该账单全部由赠送金抵扣或已全额退费，可开票现金实付金额为 0")

    rate_bps = int(tax_profile["rate_bps"])
    if rate_bps > 0:
        net_cents = int(round(net_cash_invoiceable * 10000.0 / (10000 + rate_bps)))
        tax_cents = net_cash_invoiceable - net_cents
    else:
        net_cents = net_cash_invoiceable
        tax_cents = 0

    sheet_count = 1
    if FEATURE_FLAGS.get("FAPIAO_AUTO_SPLIT_SHEET", True) and net_cash_invoiceable > FAPIAO_SINGLE_SHEET_MAX_CENTS:
        sheet_count = int(math.ceil(net_cash_invoiceable / float(FAPIAO_SINGLE_SHEET_MAX_CENTS)))

    fp_id = f"FP-{datetime.now(timezone.utc).strftime('%Y%m')}-{uuid.uuid4().hex[:6].upper()}"
    now = _now_iso()
    record = {
        "id": fp_id,
        "tenant_id": tenant_id,
        "invoice_id": invoice_id,
        "fapiao_type": fapiao_type,
        "buyer_tax_id": tax_no,
        "title": tenant["company_name"],
        "net_amount_cents": net_cents,
        "tax_amount_cents": tax_cents,
        "gross_amount_cents": net_cash_invoiceable,
        "sheet_count": sheet_count,
        "status": "ISSUED",
        "red_letter_of": None,
        "created_at": now,
    }
    insert_fapiao_request(conn, record)
    return record


def issue_red_letter_fapiao(conn: sqlite3.Connection, original_fapiao_id: str, operator: str = "finance_admin") -> Dict[str, Any]:
    """对已开具的蓝字发票执行全额红字信息表冲红。"""
    orig = get_fapiao_by_id(conn, original_fapiao_id)
    if not orig:
        raise LookupError("原蓝字发票记录不存在")
    if orig["status"] == "RED_REVERSED":
        raise ValueError("该蓝字发票已完成红字冲销")

    now = _now_iso()
    red_id = f"FP-RED-{uuid.uuid4().hex[:6].upper()}"
    red_record = {
        "id": red_id,
        "tenant_id": orig["tenant_id"],
        "invoice_id": orig["invoice_id"],
        "fapiao_type": orig["fapiao_type"],
        "buyer_tax_id": orig["buyer_tax_id"],
        "title": orig["title"],
        "net_amount_cents": -abs(int(orig["net_amount_cents"])),
        "tax_amount_cents": -abs(int(orig["tax_amount_cents"])),
        "gross_amount_cents": -abs(int(orig["gross_amount_cents"])),
        "sheet_count": 1,
        "status": "RED_ISSUED",
        "red_letter_of": original_fapiao_id,
        "created_at": now,
    }
    insert_fapiao_request(conn, red_record)
    conn.execute("UPDATE fapiao_requests SET status = 'RED_REVERSED' WHERE id = ?", (original_fapiao_id,))
    conn.execute(
        "INSERT INTO audit_logs (actor, action, target_id, detail, created_at) VALUES (?, 'RED_FAPIAO', ?, ?, ?)",
        (operator, original_fapiao_id, f"red_id={red_id}", now),
    )
    return red_record


def get_tenant_fapiao_list(conn: sqlite3.Connection, tenant_id: str) -> List[Dict[str, Any]]:
    return list_tenant_fapiaos(conn, tenant_id)
