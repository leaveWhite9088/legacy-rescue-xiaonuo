# -*- coding: utf-8 -*-
"""租户账务信用评分与授信额度风控评估模型。"""
import sqlite3
from typing import Any, Dict

from app.utils.calc_helpers import clamp_int, safe_div_bps


def compute_tenant_credit_profile(conn: sqlite3.Connection, tenant_id: str) -> Dict[str, Any]:
    """综合历史完结账单履约率、争议率、钱包现金储备比计算 300~950 信用分。"""
    tenant = conn.execute("SELECT * FROM tenants WHERE id = ?", (tenant_id,)).fetchone()
    if not tenant:
        raise LookupError(f"Tenant not found: {tenant_id}")

    inv_stats = conn.execute(
        """
        SELECT COUNT(*) AS total_cnt,
               SUM(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END) AS paid_cnt,
               SUM(CASE WHEN dispute_reason != '' THEN 1 ELSE 0 END) AS disputed_cnt,
               COALESCE(SUM(total_cents), 0) AS billed_cents
        FROM invoices
        WHERE tenant_id = ? AND status != 'VOID'
        """,
        (tenant_id,),
    ).fetchone()

    wallet = conn.execute("SELECT * FROM wallets WHERE tenant_id = ?", (tenant_id,)).fetchone()
    cash_bal = int(wallet["cash_balance_cents"]) if wallet else 0

    total_cnt = int(inv_stats["total_cnt"] or 0)
    paid_cnt = int(inv_stats["paid_cnt"] or 0)
    disputed_cnt = int(inv_stats["disputed_cnt"] or 0)
    billed_cents = int(inv_stats["billed_cents"] or 0)

    score = 680
    if tenant["tier_level"] == "VIP":
        score += 60
    if total_cnt > 0:
        pay_ratio_bps = safe_div_bps(paid_cnt, total_cnt)
        score += (pay_ratio_bps - 7000) // 40
    score -= disputed_cnt * 35

    if cash_bal >= 100_000:
        score += 45
    elif cash_bal < 0:
        score -= 150

    final_score = clamp_int(score, 300, 950)
    if final_score >= 800:
        grade = "AAA"
        recommended_credit_cents = 500_000
    elif final_score >= 700:
        grade = "AA"
        recommended_credit_cents = 200_000
    elif final_score >= 600:
        grade = "A"
        recommended_credit_cents = 50_000
    else:
        grade = "WATCH"
        recommended_credit_cents = 0

    return {
        "tenant_id": tenant_id,
        "company_name": tenant["company_name"],
        "credit_score": final_score,
        "risk_grade": grade,
        "recommended_credit_limit_cents": recommended_credit_cents,
        "metrics": {
            "invoice_count": total_cnt,
            "paid_count": paid_cnt,
            "disputed_count": disputed_cnt,
            "lifetime_billed_cents": billed_cents,
            "current_cash_cents": cash_bal,
        },
    }
