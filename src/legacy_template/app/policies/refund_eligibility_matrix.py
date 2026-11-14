# -*- coding: utf-8 -*-
"""退款合规性评估矩阵（区分合同退订、错账退款与混合资金池原路回充原则）。"""
from typing import Any, Dict


def evaluate_refund_policy(
    trigger_reason: str,
    paid_cash_cents: int,
    paid_promo_cents: int,
    prior_refunded_cents: int,
    requested_refund_cents: int,
) -> Dict[str, Any]:
    """根据《产品与账务规则》校验退款请求性质：
    - 若属于客户主动退订当期套餐（VOLUNTARY_CANCEL），基础月费可退额恒为 0；
    - 若属于账单核算差错退款或管理端冲正，退回现金部分严禁超过该单实际现金净支付额！
    """
    norm_reason = (trigger_reason or "").strip().upper()
    if norm_reason in ("VOLUNTARY_CANCEL", "MID_CYCLE_UNSUBSCRIBE"):
        return {
            "eligible": False,
            "max_cash_refundable_cents": 0,
            "max_promo_refundable_cents": 0,
            "deny_code": "NO_PRORATED_REFUND_ON_CANCEL",
        }

    total_paid = max(0, int(paid_cash_cents)) + max(0, int(paid_promo_cents))
    rem_total = max(0, total_paid - max(0, int(prior_refunded_cents)))
    if requested_refund_cents <= 0 or requested_refund_cents > rem_total:
        return {
            "eligible": False,
            "max_cash_refundable_cents": max(0, int(paid_cash_cents)),
            "max_promo_refundable_cents": max(0, int(paid_promo_cents)),
            "deny_code": "EXCEEDS_REFUNDABLE_BALANCE",
        }

    return {
        "eligible": True,
        "max_cash_refundable_cents": max(0, int(paid_cash_cents)),
        "max_promo_refundable_cents": max(0, int(paid_promo_cents)),
        "deny_code": None,
    }
