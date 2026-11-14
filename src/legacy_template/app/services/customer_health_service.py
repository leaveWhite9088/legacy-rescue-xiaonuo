# -*- coding: utf-8 -*-
"""SaaS 经营分析服务：月度经常性收入 (MRR)、净收入留存率 (NRR) 与客户流失预警画像。"""
import sqlite3
from typing import Any, Dict, List

from app.infra.config import PLANS
from app.infra.db import parse_legacy_amount_cents
from app.utils.calc_helpers import safe_div_bps


def compute_mrr_and_cohort_metrics(conn: sqlite3.Connection, current_period: str = "2026-11", prev_period: str = "2026-10") -> Dict[str, Any]:
    subs = conn.execute(
        "SELECT plan_code, status, COUNT(*) AS cnt FROM subscriptions GROUP BY plan_code, status"
    ).fetchall()

    active_mrr_cents = 0
    plan_mix: Dict[str, int] = {}
    at_risk_cancels = 0

    for r in subs:
        p_code = r["plan_code"]
        cnt = int(r["cnt"] or 0)
        plan_mix[p_code] = plan_mix.get(p_code, 0) + cnt
        if r["status"] in ("ACTIVE", "ACTIVE_LEGACY"):
            fee = int(PLANS.get(p_code, PLANS["STARTER"])["monthly_fee_cents"])
            active_mrr_cents += fee * cnt
        elif r["status"] == "CANCELLED_AT_PERIOD_END":
            at_risk_cancels += cnt

    prev_invs = conn.execute("SELECT * FROM invoices WHERE period_key = ? AND status != 'VOID'", (prev_period,)).fetchall()
    curr_invs = conn.execute("SELECT * FROM invoices WHERE period_key = ? AND status != 'VOID'", (current_period,)).fetchall()

    prev_rev = sum(parse_legacy_amount_cents(dict(x), "total_cents") for x in prev_invs)
    curr_rev = sum(parse_legacy_amount_cents(dict(x), "total_cents") for x in curr_invs)

    return {
        "current_period": current_period,
        "active_contracted_mrr_cents": active_mrr_cents,
        "estimated_arr_cents": active_mrr_cents * 12,
        "previous_period_billed_cents": prev_rev,
        "current_period_billed_to_date_cents": curr_rev,
        "period_over_period_ratio_bps": safe_div_bps(curr_rev, prev_rev) if prev_rev else 10000,
        "plan_subscriber_mix": plan_mix,
        "pending_cancellation_count": at_risk_cancels,
    }


def list_low_utilization_churn_candidates(conn: sqlite3.Connection, period_key: str = "2026-11") -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT t.id, t.company_name, s.plan_code, COALESCE(SUM(u.total_quantity), 0) AS used_qty
        FROM tenants t
        JOIN subscriptions s ON s.tenant_id = t.id
        LEFT JOIN usage_summaries u ON u.tenant_id = t.id AND u.period_key = ?
        WHERE s.status = 'ACTIVE' AND s.plan_code IN ('PRO', 'ENTERPRISE')
        GROUP BY t.id, t.company_name, s.plan_code
        ORDER BY used_qty ASC
        LIMIT 25
        """,
        (period_key,),
    ).fetchall()

    candidates: List[Dict[str, Any]] = []
    for r in rows:
        inc = int(PLANS[r["plan_code"]]["included_quota"])
        used = int(r["used_qty"] or 0)
        util_bps = safe_div_bps(used, inc)
        if util_bps < 1500:
            candidates.append({
                "tenant_id": r["id"],
                "company_name": r["company_name"],
                "plan_code": r["plan_code"],
                "used_quantity": used,
                "included_quota": inc,
                "utilization_bps": util_bps,
            })
    return candidates
