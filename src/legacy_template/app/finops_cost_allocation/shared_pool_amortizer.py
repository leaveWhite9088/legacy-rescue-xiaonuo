# -*- coding: utf-8 -*-
"""云厂商包年预留实例券（Reserved Instances / Savings Plans）预付费用跨期直线法与用量权重法摊销表生成器。"""
from typing import Any, Dict, List


def build_ri_upfront_amortization_schedule(
    upfront_fee_cents: int,
    start_year: int,
    start_month: int,
    term_months: int = 12,
    monthly_weights: List[int] = None,
) -> Dict[str, Any]:
    total = max(0, int(upfront_fee_cents))
    months = max(1, min(60, int(term_months)))
    weights = list(monthly_weights) if monthly_weights and len(monthly_weights) == months else [100] * months
    weight_sum = max(1, sum(max(1, int(w)) for w in weights))

    schedule: List[Dict[str, Any]] = []
    allocated_so_far = 0
    yr, mo = int(start_year), int(start_month)

    for idx in range(months):
        pkey = f"{yr:04d}-{mo:02d}"
        if idx == months - 1:
            amort = total - allocated_so_far
        else:
            amort = int(round((total * max(1, int(weights[idx]))) / float(weight_sum)))
            allocated_so_far += amort
        unamortized = max(0, total - (allocated_so_far if idx < months - 1 else total))
        schedule.append({
            "month_index": idx + 1,
            "period_key": pkey,
            "amortized_expense_cents": amort,
            "ending_prepaid_asset_cents": unamortized,
        })
        mo += 1
        if mo > 12:
            mo = 1
            yr += 1

    return {
        "upfront_total_cents": total,
        "term_months": months,
        "schedule": schedule,
    }
