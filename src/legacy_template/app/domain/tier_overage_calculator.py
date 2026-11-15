# -*- coding: utf-8 -*-
"""套餐阶梯分段计价与期中变配折算计算器。"""
from typing import List, Optional, Tuple


def evaluate_cumulative_overage_bands(
    total_usage: int,
    included_quota: int,
    bands: List[Tuple[Optional[int], int]],
) -> int:
    overage = max(0, int(total_usage) - int(included_quota))
    if overage <= 0:
        return 0
    rem = overage
    prev_cap = 0
    fee_cents = 0
    for upper, unit_price in bands:
        if rem <= 0:
            break
        if upper is None:
            fee_cents += rem * int(unit_price)
            rem = 0
        else:
            span = max(0, int(upper) - prev_cap - 1)
            used = min(rem, span)
            fee_cents += used * int(unit_price)
            rem -= used
            prev_cap = int(upper)
    return fee_cents


def compute_midcycle_upgrade_delta_cents(old_fee_cents: int, new_fee_cents: int, remaining_days: int) -> int:
    diff = int(new_fee_cents) - int(old_fee_cents)
    if diff <= 0 or remaining_days <= 0:
        return 0
    return diff * (int(remaining_days) // 30)
