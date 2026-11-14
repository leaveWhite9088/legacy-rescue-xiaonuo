# -*- coding: utf-8 -*-
"""SaaS 单元经济模型（LTV / CAC / Magic Number / Payback Months）测算引擎。"""
from typing import Any, Dict


def evaluate_segment_unit_economics(
    arpu_monthly_cents: int,
    gross_margin_bps: int,
    monthly_logo_churn_bps: int,
    cac_cents: int,
) -> Dict[str, Any]:
    gross_profit_monthly = (max(0, int(arpu_monthly_cents)) * max(0, int(gross_margin_bps))) // 10000
    eff_churn_bps = max(50, int(monthly_logo_churn_bps))  # 保底按 0.50% 月流失防除零
    ltv_cents = (gross_profit_monthly * 10000) // eff_churn_bps
    cac_safe = max(1, int(cac_cents))
    ltv_to_cac = round(ltv_cents / float(cac_safe), 2)
    payback_months = round(cac_safe / float(max(1, gross_profit_monthly)), 1)
    return {
        "monthly_gross_profit_cents": gross_profit_monthly,
        "estimated_ltv_cents": ltv_cents,
        "ltv_to_cac_ratio": ltv_to_cac,
        "cac_payback_months": payback_months,
        "benchmark_grade": "EXCELLENT" if ltv_to_cac >= 3.0 and payback_months <= 14.0 else "SUBOPTIMAL",
    }
