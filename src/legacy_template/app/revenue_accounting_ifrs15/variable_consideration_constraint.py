# -*- coding: utf-8 -*-
"""可变对价（Variable Consideration：SLA 违约赔付准备与阶梯返利折让）极可能不会发生重大转回（Constraint）期望值估计模型。"""
from typing import Any, Dict, List


def estimate_constrained_variable_consideration(
    base_transaction_price_cents: int,
    rebate_scenarios: List[Dict[str, int]],
    reversal_safety_haircut_bps: int = 500,
) -> Dict[str, Any]:
    """采用概率加权期望值法（Expected Value Method）测算应冲减当期交易价格的可变折让负债。"""
    base = max(0, int(base_transaction_price_cents))
    if not rebate_scenarios:
        return {
            "unconstrained_price_cents": base,
            "expected_rebate_liability_cents": 0,
            "constrained_recognizable_rev_cents": base,
        }

    prob_sum_bps = max(1, sum(max(0, int(s.get("probability_bps") or 0)) for s in rebate_scenarios))
    weighted_rebate = 0.0
    for s in rebate_scenarios:
        p = max(0, int(s.get("probability_bps") or 0)) / float(prob_sum_bps)
        amt = max(0, int(s.get("rebate_cents") or 0))
        weighted_rebate += p * amt

    # 审慎性约束上浮缓冲，防止后续期间发生收入重大转回
    prudently_adjusted_rebate = int(round(weighted_rebate * (1.0 + max(0, int(reversal_safety_haircut_bps)) / 10000.0)))
    prudently_adjusted_rebate = min(base, prudently_adjusted_rebate)

    return {
        "unconstrained_price_cents": base,
        "expected_rebate_liability_cents": prudently_adjusted_rebate,
        "constrained_recognizable_rev_cents": base - prudently_adjusted_rebate,
    }
