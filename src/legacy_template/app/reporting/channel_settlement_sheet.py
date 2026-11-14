# -*- coding: utf-8 -*-
"""渠道生态代理商季度/月度净实收对账结算单与退费扣回（Clawback）明细生成器。"""
import sqlite3
from typing import Any, Dict, List

from app.infra.config import PARTNER_TIERS


def build_partner_settlement_statement(conn: sqlite3.Connection, partner_code: str, period_key: str) -> Dict[str, Any]:
    refs = conn.execute(
        """
        SELECT pr.tenant_id, pr.partner_tier, pr.bound_at, t.company_name
        FROM partner_referrals pr
        JOIN tenants t ON t.id = pr.tenant_id
        WHERE pr.partner_code = ?
        ORDER BY pr.tenant_id ASC
        """,
        (partner_code,),
    ).fetchall()

    if not refs:
        return {
            "partner_code": partner_code,
            "period_key": period_key,
            "referred_tenants": 0,
            "net_cash_eligible_cents": 0,
            "commission_cents": 0,
            "line_items": [],
        }

    tier = refs[0]["partner_tier"]
    rate_bps = int(PARTNER_TIERS.get(tier, PARTNER_TIERS["SILVER"])["rate_bps"])
    line_items: List[Dict[str, Any]] = []
    net_cash_sum = 0

    for ref in refs:
        tid = ref["tenant_id"]
        invs = conn.execute(
            "SELECT id, total_cents, refunded_cents, status FROM invoices WHERE tenant_id = ? AND period_key = ? AND status != 'VOID'",
            (tid, period_key),
        ).fetchall()
        for inv in invs:
            pay = conn.execute(
                "SELECT COALESCE(SUM(cash_paid_cents), 0) AS cash_c, COALESCE(SUM(promo_paid_cents), 0) AS promo_c FROM invoice_payments WHERE invoice_id = ?",
                (inv["id"],),
            ).fetchone()
            cash_c = int(pay["cash_c"] or 0) if pay else 0
            promo_c = int(pay["promo_c"] or 0) if pay else 0
            ref_c = int(inv["refunded_cents"] or 0)
            # 渠道规则：赠送金不计提返佣；若发生退款先冲减可计提现金基数
            eligible_cash = max(0, cash_c - ref_c)
            comm = (eligible_cash * rate_bps) // 10000
            net_cash_sum += eligible_cash
            line_items.append({
                "tenant_id": tid,
                "company_name": ref["company_name"],
                "invoice_id": inv["id"],
                "cash_paid_cents": cash_c,
                "promo_paid_cents": promo_c,
                "refund_clawback_cents": min(cash_c, ref_c),
                "eligible_cash_cents": eligible_cash,
                "commission_cents": comm,
            })

    return {
        "partner_code": partner_code,
        "partner_tier": tier,
        "rate_bps": rate_bps,
        "period_key": period_key,
        "referred_tenants": len(refs),
        "net_cash_eligible_cents": net_cash_sum,
        "commission_cents": (net_cash_sum * rate_bps) // 10000,
        "line_items": line_items,
    }
