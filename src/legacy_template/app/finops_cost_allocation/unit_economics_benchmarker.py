# -*- coding: utf-8 -*-
"""SaaS 核心资本市场经营效率指标（Rule of 40、LTV/CAC、CAC 回收期、Magic Number）测算引擎。"""
from typing import Any, Dict


def evaluate_saas_unit_economics(
    current_quarter_arr_cents: int,
    prior_quarter_arr_cents: int,
    yoy_revenue_growth_bps: int,
    ebitda_margin_bps: int,
    prior_quarter_sales_marketing_cents: int,
    gross_margin_bps: int = 7800,
    annual_logo_churn_bps: int = 800,
    arpa_monthly_cents: int = 65_000,
) -> Dict[str, Any]:
    """综合增长率与利润率评估 SaaS 健康度，供管理层月度经营分析会（MBR）使用。"""
    net_new_arr = int(current_quarter_arr_cents) - int(prior_quarter_arr_cents)
    sm_spend = max(1, int(prior_quarter_sales_marketing_cents))
    magic_number_x100 = int(round((net_new_arr * 100.0) / sm_spend))

    rule_of_40_bps = int(yoy_revenue_growth_bps) + int(ebitda_margin_bps)
    monthly_churn_rate = max(0.001, (annual_logo_churn_bps / 10000.0) / 12.0)
    gm_ratio = max(0.05, min(0.99, gross_margin_bps / 10000.0))

    ltv_cents = int(round((arpa_monthly_cents * gm_ratio) / monthly_churn_rate))
    assumed_cac_cents = max(1, int(arpa_monthly_cents * 11))
    ltv_to_cac_x10 = int(round((ltv_cents * 10.0) / assumed_cac_cents))
    cac_payback_months = round(assumed_cac_cents / max(1.0, arpa_monthly_cents * gm_ratio), 1)

    return {
        "net_new_arr_cents": net_new_arr,
        "saas_magic_number_x100": magic_number_x100,
        "rule_of_40_score_bps": rule_of_40_bps,
        "beats_rule_of_40": rule_of_40_bps >= 4000,
        "estimated_ltv_cents": ltv_cents,
        "assumed_cac_cents": assumed_cac_cents,
        "ltv_to_cac_ratio_x10": ltv_to_cac_x10,
        "cac_payback_months": cac_payback_months,
    }
