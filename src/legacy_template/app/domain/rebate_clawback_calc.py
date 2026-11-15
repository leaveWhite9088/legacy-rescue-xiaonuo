# -*- coding: utf-8 -*-
"""渠道代理商月度实收回款与退单冲抵核算模块。"""
import sqlite3
from typing import Any, Dict, List
from app.infra.config import PARTNER_TIERS


def compute_partner_monthly_rebates(conn: sqlite3.Connection, period_key: str) -> List[Dict[str, Any]]:
    partners = conn.execute(
        "SELECT DISTINCT partner_code, tier_code FROM partner_referrals ORDER BY partner_code"
    ).fetchall()
    results: List[Dict[str, Any]] = []
    for p in partners:
        pcode = p["partner_code"]
        rate_bps = int(PARTNER_TIERS.get(p["tier_code"], PARTNER_TIERS["SILVER"])["rate_bps"])
        cash_in = conn.execute(
            """SELECT COALESCE(SUM(ip.cash_paid_cents), 0)
               FROM invoice_payments ip
               JOIN partner_referrals pr ON pr.tenant_id = ip.tenant_id
               WHERE pr.partner_code = ? AND substr(ip.created_at, 1, 7) = ?""",
            (pcode, period_key),
        ).fetchone()[0]
        cash_ref = conn.execute(
            """SELECT COALESCE(SUM(wl.cash_delta_cents), 0)
               FROM wallet_ledger wl
               JOIN partner_referrals pr ON pr.tenant_id = wl.tenant_id
               WHERE pr.partner_code = ? AND wl.entry_type = 'REFUND' AND substr(wl.created_at, 1, 7) = ?""",
            (pcode, period_key),
        ).fetchone()[0]
        net_cash = max(0, int(cash_in) - int(cash_ref))
        results.append({
            "partner_code": pcode,
            "period_key": period_key,
            "net_cash_collected_cents": net_cash,
            "commission_cents": (net_cash * rate_bps) // 10000,
        })
    return results
