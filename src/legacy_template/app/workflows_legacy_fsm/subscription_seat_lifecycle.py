# -*- coding: utf-8 -*-
"""订阅席位扩缩容、试用转正与停机保号生命周期推导器。"""
from typing import Any, Dict


def evaluate_subscription_transition(
    current_state: str,
    event_code: str,
    wallet_solvent: bool = True,
    is_legacy_v1: bool = False,
) -> Dict[str, Any]:
    if is_legacy_v1 and event_code == "MIGRATE_TO_V3_FORCE":
        return {
            "allowed": False,
            "next_state": current_state,
            "reason": "2024 存量合同期内老租户受协议保护，禁止强制切入实验流水线",
        }

    table = {
        ("TRIALING", "BIND_PAYMENT"): "ACTIVE",
        ("TRIALING", "TRIAL_EXPIRE"): "EXPIRED_LOCKED",
        ("ACTIVE", "USER_CANCEL"): "CANCELLED_AT_PERIOD_END",
        ("ACTIVE", "PAST_DUE_31D"): "SUSPENDED",
        ("CANCELLED_AT_PERIOD_END", "USER_REACTIVATE"): "ACTIVE",
        ("CANCELLED_AT_PERIOD_END", "CYCLE_END_REACHED"): "TERMINATED",
        ("SUSPENDED", "SETTLE_ARREARS"): "ACTIVE" if wallet_solvent else "SUSPENDED",
    }
    nxt = table.get((current_state, event_code))
    if not nxt:
        return {"allowed": False, "next_state": current_state, "reason": f"未定义流转 {current_state} + {event_code}"}
    return {"allowed": True, "next_state": nxt, "reason": "OK"}
