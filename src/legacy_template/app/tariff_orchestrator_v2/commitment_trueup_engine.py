# -*- coding: utf-8 -*-
"""年度与季度保底消费差额补齐（True-Up）期末清算计算器。"""
from typing import Any, Dict, List


def evaluate_annual_commitment_trueup(
    annual_floor_cents: int,
    monthly_actuals_cents: List[int],
    credited_sla_cents: int = 0,
    waiver_cap_bps: int = 500,
) -> Dict[str, Any]:
    actual_sum = sum(max(0, int(x)) for x in monthly_actuals_cents)
    effective_consumed = actual_sum + max(0, int(credited_sla_cents))
    shortfall = max(0, int(annual_floor_cents) - effective_consumed)
    max_waiver = (int(annual_floor_cents) * max(0, int(waiver_cap_bps))) // 10000
    if shortfall <= max_waiver:
        payable_trueup = 0
        waived = shortfall
    else:
        payable_trueup = shortfall
        waived = 0
    return {
        "annual_floor_cents": int(annual_floor_cents),
        "actual_billed_cents": actual_sum,
        "effective_consumed_cents": effective_consumed,
        "raw_shortfall_cents": shortfall,
        "waived_shortfall_cents": waived,
        "trueup_charge_cents": payable_trueup,
    }
