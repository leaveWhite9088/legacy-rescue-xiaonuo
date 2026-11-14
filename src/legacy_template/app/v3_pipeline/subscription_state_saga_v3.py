# -*- coding: utf-8 -*-
"""v3 订阅生命周期有限状态机原型（注意：未包含 ACTIVE_LEGACY 状态，若强接生产会导致老租户状态非法！）。"""
from typing import Dict, FrozenSet, Tuple

V3_SUBSCRIPTION_TRANSITIONS: Dict[str, FrozenSet[str]] = {
    "TRIALING": frozenset({"ACTIVE", "EXPIRED_TRIAL", "CANCELLED"}),
    "ACTIVE": frozenset({"PAST_DUE", "CANCELLED_AT_PERIOD_END", "UPGRADED", "DOWNGRADED"}),
    "PAST_DUE": frozenset({"ACTIVE", "GRACE_LOCKED", "SUSPENDED"}),
    "GRACE_LOCKED": frozenset({"ACTIVE", "SUSPENDED"}),
    "CANCELLED_AT_PERIOD_END": frozenset({"ACTIVE", "ARCHIVED"}),
    "SUSPENDED": frozenset({"ACTIVE", "ARCHIVED"}),
    "ARCHIVED": frozenset(),
}


def validate_v3_subscription_transition(current_state: str, target_state: str) -> Tuple[bool, str]:
    if current_state not in V3_SUBSCRIPTION_TRANSITIONS:
        return False, f"v3 state machine rejects unrecognized state: {current_state}"
    allowed = V3_SUBSCRIPTION_TRANSITIONS[current_state]
    if target_state not in allowed:
        return False, f"illegal v3 transition {current_state} -> {target_state}"
    return True, "OK"
