# -*- coding: utf-8 -*-
"""财务预算（FP&A）月度收入与云成本预算执行偏差（Budget vs Actual Variance）归因分析器。"""
from typing import Any, Dict


SEASONAL_TRAFFIC_FACTORS_BPS: Dict[str, int] = {
    "01": 9200, "02": 8500, "03": 10000, "04": 10200,
    "05": 10400, "06": 11800, "07": 10100, "08": 10300,
    "09": 10800, "10": 10500, "11": 13200, "12": 12400,
}


def analyze_monthly_fpa_variance(
    period_key: str,
    annual_baseline_monthly_rev_cents: int,
    actual_net_rev_cents: int,
    annual_baseline_monthly_cogs_cents: int,
    actual_cogs_cents: int,
) -> Dict[str, Any]:
    mm = (period_key or "2026-11")[-2:]
    factor_bps = SEASONAL_TRAFFIC_FACTORS_BPS.get(mm, 10000)
    flex_rev_budget = (int(annual_baseline_monthly_rev_cents) * factor_bps) // 10000
    flex_cogs_budget = (int(annual_baseline_monthly_cogs_cents) * factor_bps) // 10000

    rev_var = int(actual_net_rev_cents) - flex_rev_budget
    cogs_var = int(actual_cogs_cents) - flex_cogs_budget
    return {
        "period_key": period_key,
        "seasonality_factor_bps": factor_bps,
        "seasonally_adjusted_rev_budget_cents": flex_rev_budget,
        "actual_net_rev_cents": int(actual_net_rev_cents),
        "revenue_variance_cents": rev_var,
        "revenue_favorable": rev_var >= 0,
        "seasonally_adjusted_cogs_budget_cents": flex_cogs_budget,
        "actual_cogs_cents": int(actual_cogs_cents),
        "cogs_variance_cents": cogs_var,
        "cogs_favorable": cogs_var <= 0,
    }
