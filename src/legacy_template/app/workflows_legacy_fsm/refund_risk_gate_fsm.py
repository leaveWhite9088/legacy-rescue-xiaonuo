# -*- coding: utf-8 -*-
"""退费反洗钱（AML）与原路退回风控拦截状态机。"""
from typing import Any, Dict


def evaluate_refund_aml_gate(
    refund_cents: int,
    cash_paid_cents: int,
    promo_paid_cents: int,
    days_since_topup: int,
    fapiao_already_issued: bool,
    fapiao_red_reversed: bool,
) -> Dict[str, Any]:
    flags = []
    if fapiao_already_issued and not fapiao_red_reversed:
        return {
            "decision": "BLOCK_REQUIRE_RED_FAPIAO",
            "max_cash_refund_cents": 0,
            "flags": ["BLUE_FAPIAO_NOT_REVERSED"],
        }

    max_cash = max(0, int(cash_paid_cents))
    if refund_cents > max_cash + max(0, int(promo_paid_cents)):
        return {
            "decision": "BLOCK_OVER_REFUND",
            "max_cash_refund_cents": max_cash,
            "flags": ["EXCEEDS_TOTAL_PAID"],
        }

    if days_since_topup <= 2 and refund_cents >= 100_000:
        flags.append("RAPID_TOPUP_WITHDRAWAL_REVIEW")

    cash_portion = min(int(refund_cents), max_cash)
    promo_portion = max(0, int(refund_cents) - cash_portion)
    decision = "MANUAL_FINANCE_REVIEW" if flags else "AUTO_APPROVE_BUCKET_SPLIT"
    return {
        "decision": decision,
        "max_cash_refund_cents": max_cash,
        "recommended_cash_back_cents": cash_portion,
        "recommended_promo_back_cents": promo_portion,
        "flags": flags,
    }
