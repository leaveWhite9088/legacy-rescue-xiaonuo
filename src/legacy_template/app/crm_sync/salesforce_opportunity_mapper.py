# -*- coding: utf-8 -*-
"""CRM 商机（Opportunity）与云测计费主档双向映射、ARR/ACV/TCV 签单口径折算及多币种牌价换算器。"""
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.infra.config import PLANS


STAGE_WIN_PROBABILITY_BPS: Dict[str, int] = {
    "01_DISCOVERY": 1000,
    "02_TECHNICAL_POC": 3000,
    "03_COMMERCIAL_PROPOSAL": 5500,
    "04_LEGAL_REDLINE": 8000,
    "05_CLOSED_WON": 10000,
    "06_CLOSED_LOST": 0,
}

FX_PEG_TO_CNY_MICRO: Dict[str, int] = {
    "CNY": 1_000_000,
    "USD": 7_185_000,
    "HKD": 923_500,
    "SGD": 5_362_000,
    "EUR": 7_790_000,
}


@dataclass(frozen=True)
class CrmOpportunityPayload:
    opp_id: str
    account_name: str
    stage_code: str
    target_plan_code: str
    contract_term_months: int
    quoted_currency: str
    quoted_monthly_commit_minor: int
    one_time_onboarding_fee_minor: int = 0
    sales_owner_id: str = "ae_east_01"
    region_code: str = "CN-EAST"


def convert_minor_to_cny_cents(amount_minor: int, currency: str) -> int:
    """将外币最小辅币单位（美分/港仙/新分）按财务月度记账汇率折算为人民币分。"""
    cur = (currency or "CNY").upper()
    rate_micro = FX_PEG_TO_CNY_MICRO.get(cur, 1_000_000)
    return int(round((int(amount_minor) * rate_micro) / 1_000_000.0))


def map_opportunity_to_booking_metrics(opp: CrmOpportunityPayload) -> Dict[str, Any]:
    """根据 SaaS 财务签单准则计算 TCV（总合同额）、ACV（年化合同额）、ARR（经常性年收入）与加权预测值。"""
    months = max(1, min(60, int(opp.contract_term_months)))
    plan = PLANS.get(opp.target_plan_code, PLANS["PRO"])
    std_monthly_cny = int(plan["monthly_fee_cents"])

    commit_cny = convert_minor_to_cny_cents(opp.quoted_monthly_commit_minor, opp.quoted_currency)
    effective_monthly_cny = max(std_monthly_cny, commit_cny)
    onboarding_cny = convert_minor_to_cny_cents(opp.one_time_onboarding_fee_minor, opp.quoted_currency)

    recurring_tcv_cny = effective_monthly_cny * months
    total_tcv_cny = recurring_tcv_cny + onboarding_cny
    arr_cny = effective_monthly_cny * 12
    acv_cny = recurring_tcv_cny if months < 12 else arr_cny + (onboarding_cny * 12) // months

    prob_bps = STAGE_WIN_PROBABILITY_BPS.get(opp.stage_code, 3000)
    weighted_acv_cny = (acv_cny * prob_bps) // 10000

    return {
        "opp_id": opp.opp_id,
        "account_name": opp.account_name,
        "stage_code": opp.stage_code,
        "win_probability_bps": prob_bps,
        "target_plan_code": opp.target_plan_code,
        "contract_term_months": months,
        "effective_monthly_recurring_cents": effective_monthly_cny,
        "one_time_onboarding_cents": onboarding_cny,
        "arr_cents": arr_cny,
        "acv_cents": acv_cny,
        "tcv_cents": total_tcv_cny,
        "weighted_pipeline_acv_cents": weighted_acv_cny,
        "sales_owner_id": opp.sales_owner_id,
        "region_code": opp.region_code,
    }


def summarize_regional_pipeline(opportunities: List[CrmOpportunityPayload]) -> Dict[str, Any]:
    by_region: Dict[str, Dict[str, int]] = {}
    total_weighted = 0
    closed_won_arr = 0

    for opp in opportunities:
        m = map_opportunity_to_booking_metrics(opp)
        reg = m["region_code"]
        bucket = by_region.setdefault(
            reg,
            {"deal_count": 0, "raw_tcv_cents": 0, "weighted_acv_cents": 0, "closed_won_arr_cents": 0},
        )
        bucket["deal_count"] += 1
        bucket["raw_tcv_cents"] += m["tcv_cents"]
        bucket["weighted_acv_cents"] += m["weighted_acv_cents"] if "weighted_acv_cents" in m else m["weighted_pipeline_acv_cents"]
        total_weighted += m["weighted_pipeline_acv_cents"]
        if opp.stage_code == "05_CLOSED_WON":
            bucket["closed_won_arr_cents"] += m["arr_cents"]
            closed_won_arr += m["arr_cents"]

    return {
        "opportunity_count": len(opportunities),
        "total_weighted_pipeline_acv_cents": total_weighted,
        "closed_won_arr_cents": closed_won_arr,
        "by_region": by_region,
    }
