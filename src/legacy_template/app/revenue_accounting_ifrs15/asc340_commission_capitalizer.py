# -*- coding: utf-8 -*-
"""ASC 340-40 / CAS 14 合同取得增量成本（销售签约佣金资产化与客户预期受益期摊销）台账计算器。
实务准则：若预计摊销期不超过 1 年（<= 12 个月），适用实务简化处理（Practical Expedient）于发生当期直接计入销售费用；
若大客户多年期合同或预期客户存续受益期为 36 个月，则将首签增量佣金资本化为“合同取得成本”并按月直线摊销。
"""
from typing import Any, Dict, List


def build_commission_capitalization_schedule(
    deal_id: str,
    incremental_commission_cents: int,
    contract_months: int,
    expected_customer_benefit_months: int = 36,
    apply_1yr_practical_expedient: bool = True,
) -> Dict[str, Any]:
    comm = max(0, int(incremental_commission_cents))
    c_months = max(1, int(contract_months))
    b_months = max(c_months, int(expected_customer_benefit_months))

    if apply_1yr_practical_expedient and c_months <= 12 and comm < 200_000:
        return {
            "deal_id": deal_id,
            "capitalized": False,
            "treatment": "EXPENSED_IMMEDIATELY_UNDER_PRACTICAL_EXPEDIENT",
            "immediate_expense_cents": comm,
            "amortization_months": 0,
            "monthly_schedule": [],
        }

    monthly_amort = comm // b_months
    tail = comm - (monthly_amort * b_months)
    schedule: List[Dict[str, int]] = []
    carrying = comm

    for m in range(1, b_months + 1):
        charge = monthly_amort + (tail if m == b_months else 0)
        carrying -= charge
        schedule.append({
            "month_seq": m,
            "amortization_expense_cents": charge,
            "ending_deferred_asset_cents": carrying,
        })

    return {
        "deal_id": deal_id,
        "capitalized": True,
        "treatment": "CAPITALIZED_ASC_340_40_DEFERRED_CONTRACT_COST",
        "initial_asset_cents": comm,
        "amortization_months": b_months,
        "monthly_schedule": schedule,
    }
