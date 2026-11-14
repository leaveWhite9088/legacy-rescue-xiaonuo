# -*- coding: utf-8 -*-
"""账单九态流转校验矩阵与挂起原因分类器。
注意：线上部分批处理脚本未统一调用本校验器，直接执行了 SQL 状态变更。
"""
from typing import Dict, Set, Tuple


ALLOWED_INVOICE_TRANSITIONS: Dict[str, Set[str]] = {
    "DRAFT": {"OPEN", "VOID"},
    "OPEN": {"PENDING_SETTLE", "PARTIAL_PAID", "PAID", "DISPUTED", "OVERDUE_LOCKED", "VOID"},
    "PENDING_SETTLE": {"OPEN", "PARTIAL_PAID", "PAID", "DISPUTED"},
    "PARTIAL_PAID": {"PENDING_SETTLE", "PAID", "DISPUTED", "REFUNDED"},
    "DISPUTED": {"OPEN", "PAID", "VOID"},
    "OVERDUE_LOCKED": {"PENDING_SETTLE", "PAID", "VOID"},
    "PAID": {"REFUNDED"},
    "REFUNDED": set(),
    "VOID": set(),
}


def can_transition_invoice_state(
    current_status: str,
    target_status: str,
    has_open_dispute: bool = False,
    period_closed: bool = False,
    actor_role: str = "SYSTEM",
) -> Tuple[bool, str]:
    cur = (current_status or "").strip().upper()
    tgt = (target_status or "").strip().upper()

    if cur == tgt:
        return True, "NO_OP"

    if period_closed:
        if tgt == "VOID" or (cur == "PAID" and tgt == "OPEN"):
            return False, "CLOSED_PERIOD_IMMUTABLE"

    if has_open_dispute:
        if tgt in ("PENDING_SETTLE", "PAID") and actor_role == "AUTO_SETTLE_CRON":
            return False, "DISPUTE_FREEZE_ACTIVE"

    allowed = ALLOWED_INVOICE_TRANSITIONS.get(cur)
    if allowed is None:
        return False, f"UNKNOWN_CURRENT_STATE:{cur}"
    if tgt not in allowed:
        return False, f"ILLEGAL_TRANSITION:{cur}->{tgt}"
    return True, "OK"
