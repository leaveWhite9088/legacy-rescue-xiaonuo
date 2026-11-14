# -*- coding: utf-8 -*-
"""大型集团客户（母公司-全资/控股子公司）多租户账单合并视图与集团授信额度共享模拟器。"""
import sqlite3
from typing import Any, Dict, List

from app.infra.db import parse_legacy_amount_cents


def build_conglomerate_billing_rollup(
    conn: sqlite3.Connection,
    parent_tenant_id: str,
    subsidiary_tenant_ids: List[str],
    period_key: str = "2026-11",
) -> Dict[str, Any]:
    """汇总母公司及下属关联租户在指定账期的总开票额、已付额、争议冻结额及集团合并钱包头寸。"""
    member_ids = [parent_tenant_id] + [tid for tid in subsidiary_tenant_ids if tid != parent_tenant_id]
    member_summaries: List[Dict[str, Any]] = []

    group_billed = 0
    group_paid = 0
    group_cash_wallet = 0
    group_promo_wallet = 0
    group_usage_qty = 0

    for tid in member_ids:
        t_row = conn.execute("SELECT id, company_name, status FROM tenants WHERE id = ?", (tid,)).fetchone()
        if not t_row:
            continue
        w_row = conn.execute("SELECT cash_balance_cents, promo_balance_cents FROM wallets WHERE tenant_id = ?", (tid,)).fetchone()
        invs = conn.execute(
            "SELECT * FROM invoices WHERE tenant_id = ? AND period_key = ? AND status != 'VOID'",
            (tid, period_key),
        ).fetchall()
        u_row = conn.execute(
            "SELECT COALESCE(SUM(total_quantity), 0) AS qty FROM usage_summaries WHERE tenant_id = ? AND period_key = ?",
            (tid, period_key),
        ).fetchone()

        t_billed = sum(parse_legacy_amount_cents(dict(r), "total_cents") for r in invs)
        t_paid = sum(parse_legacy_amount_cents(dict(r), "paid_cents") for r in invs)
        c_bal = int(w_row["cash_balance_cents"] or 0) if w_row else 0
        p_bal = int(w_row["promo_balance_cents"] or 0) if w_row else 0
        qty = int(u_row["qty"] or 0) if u_row else 0

        group_billed += t_billed
        group_paid += t_paid
        group_cash_wallet += c_bal
        group_promo_wallet += p_bal
        group_usage_qty += qty

        member_summaries.append({
            "tenant_id": tid,
            "role": "PARENT_HQ" if tid == parent_tenant_id else "SUBSIDIARY",
            "company_name": t_row["company_name"],
            "status": t_row["status"],
            "period_billed_cents": t_billed,
            "period_paid_cents": t_paid,
            "period_unpaid_cents": max(0, t_billed - t_paid),
            "cash_wallet_cents": c_bal,
            "promo_wallet_cents": p_bal,
            "period_usage_quantity": qty,
        })

    group_unpaid = max(0, group_billed - group_paid)
    # 集团合并现金池可覆盖未结清账单比例（赠送金不可跨法人实体混用）
    cash_coverage_bps = int((group_cash_wallet * 10000) // max(1, group_unpaid)) if group_unpaid > 0 else 10000

    return {
        "parent_tenant_id": parent_tenant_id,
        "period_key": period_key,
        "member_count": len(member_summaries),
        "consolidated_billed_cents": group_billed,
        "consolidated_paid_cents": group_paid,
        "consolidated_unpaid_cents": group_unpaid,
        "consolidated_cash_wallet_cents": group_cash_wallet,
        "consolidated_promo_wallet_cents": group_promo_wallet,
        "consolidated_usage_quantity": group_usage_qty,
        "parent_cash_coverage_bps": min(99999, cash_coverage_bps),
        "members": member_summaries,
    }
