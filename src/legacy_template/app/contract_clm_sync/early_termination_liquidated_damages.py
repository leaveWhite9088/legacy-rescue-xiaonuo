# -*- coding: utf-8 -*-
"""企业年框提前解约违约金（Liquidated Damages）与历史已享年付折扣追缴计算器。"""
from typing import Any, Dict


def compute_early_termination_settlement(
    contract_monthly_cents: int,
    list_price_monthly_cents: int,
    elapsed_months: int,
    total_committed_months: int = 12,
    termination_cause: str = "CUSTOMER_CONVENIENCE",
    unconsumed_prepaid_cents: int = 0,
) -> Dict[str, Any]:
    el = max(0, int(elapsed_months))
    tot = max(1, int(total_committed_months))
    rem_months = max(0, tot - el)

    if termination_cause in ("FORCE_MAJEURE", "PROVIDER_SLA_CHRONIC_BREACH"):
        return {
            "termination_cause": termination_cause,
            "discount_clawback_cents": 0,
            "remaining_commit_penalty_cents": 0,
            "gross_penalty_cents": 0,
            "net_refund_or_collect_cents": -max(0, int(unconsumed_prepaid_cents)),
        }

    monthly_discount = max(0, int(list_price_monthly_cents) - int(contract_monthly_cents))
    clawback = monthly_discount * el

    if rem_months >= 6:
        penalty_rate_bps = 5000  # 剩余半年以上按剩余承诺额 50% 计收违约金
    elif rem_months >= 3:
        penalty_rate_bps = 3500
    else:
        penalty_rate_bps = 2000

    rem_commit_value = int(contract_monthly_cents) * rem_months
    rem_penalty = (rem_commit_value * penalty_rate_bps) // 10000
    gross_penalty = clawback + rem_penalty
    net_due = gross_penalty - max(0, int(unconsumed_prepaid_cents))

    return {
        "termination_cause": termination_cause,
        "remaining_months": rem_months,
        "discount_clawback_cents": clawback,
        "remaining_commit_penalty_cents": rem_penalty,
        "gross_penalty_cents": gross_penalty,
        "net_refund_or_collect_cents": net_due,
    }
