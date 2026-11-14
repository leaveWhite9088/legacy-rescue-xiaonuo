# -*- coding: utf-8 -*-
"""租户月内 API 配额消耗速率预测 (Burn-Rate Forecast) 与智能升配建议引擎。"""
import sqlite3
from typing import Any, Dict, List

from app.billing_ext.cpq_deal_desk import compare_standard_plans_for_workload
from app.domain.pricing import compute_tiered_overage_cents
from app.infra.config import PLANS


def forecast_tenant_month_end_usage(
    conn: sqlite3.Connection,
    tenant_id: str,
    period_key: str = "2026-11",
    elapsed_days_in_month: int = 13,
    total_days_in_month: int = 30,
) -> Dict[str, Any]:
    """根据当月前 N 天已发生用量（已刷盘汇总 + 未刷盘缓冲）线性与平滑外推月末调用量及预计超额账单。"""
    tenant = conn.execute("SELECT * FROM tenants WHERE id = ?", (tenant_id,)).fetchone()
    if not tenant:
        raise LookupError(f"Tenant not found: {tenant_id}")

    sub = conn.execute(
        "SELECT * FROM subscriptions WHERE tenant_id = ? ORDER BY updated_at DESC LIMIT 1",
        (tenant_id,),
    ).fetchone()
    plan_code = sub["plan_code"] if sub else "STARTER"
    spec = PLANS.get(plan_code, PLANS["STARTER"])

    s_row = conn.execute(
        "SELECT COALESCE(SUM(total_quantity), 0) AS q FROM usage_summaries WHERE tenant_id = ? AND period_key = ?",
        (tenant_id, period_key),
    ).fetchone()
    u_row = conn.execute(
        "SELECT COALESCE(SUM(quantity), 0) AS q FROM usage_events WHERE tenant_id = ? AND period_key = ? AND flushed = 0",
        (tenant_id, period_key),
    ).fetchone()

    mtd_qty = int(s_row["q"] or 0) + int(u_row["q"] or 0)
    e_days = max(1, min(total_days_in_month, int(elapsed_days_in_month)))
    daily_velocity = mtd_qty / float(e_days)
    projected_eom_qty = int(round(daily_velocity * int(total_days_in_month)))

    included = int(spec["included_quota"])
    days_until_exhaustion = None
    if daily_velocity > 0:
        if mtd_qty >= included:
            days_until_exhaustion = 0
        else:
            days_until_exhaustion = int(round((included - mtd_qty) / daily_velocity))

    projected_overage_cents = compute_tiered_overage_cents(
        projected_eom_qty,
        included,
        spec["overage_tiers"],
    )
    projected_bill_cents = int(spec["monthly_fee_cents"]) + projected_overage_cents

    plan_comparison = None
    if not spec.get("is_legacy"):
        plan_comparison = compare_standard_plans_for_workload(
            projected_monthly_calls=projected_eom_qty,
            tax_profile_code=tenant["tax_profile_code"] or "CN_VAT_6_INCLUSIVE",
        )

    return {
        "tenant_id": tenant_id,
        "period_key": period_key,
        "current_plan_code": plan_code,
        "mtd_quantity": mtd_qty,
        "daily_burn_rate": round(daily_velocity, 1),
        "projected_eom_quantity": projected_eom_qty,
        "included_quota": included,
        "estimated_days_until_quota_exhausted": days_until_exhaustion,
        "projected_overage_fee_cents": projected_overage_cents,
        "projected_pretax_bill_cents": projected_bill_cents,
        "optimal_plan_analysis": plan_comparison,
    }
