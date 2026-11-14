# -*- coding: utf-8 -*-
"""高风险后付费定制客户履约保证金（Security Deposit）台账核算与期末清退冲抵测算器。
规则提示：履约保证金独立于预收现金钱包，仅在合同期满且无未结清账单、无未决争议时方可原路退还。
"""
from typing import Any, Dict, List


def evaluate_deposit_release_eligibility(
    tenant_id: str,
    held_deposit_cents: int,
    open_invoices: List[Dict[str, Any]],
    contract_terminated: bool,
) -> Dict[str, Any]:
    deposit = max(0, int(held_deposit_cents))
    unpaid_sum = 0
    disputed_cnt = 0

    for inv in open_invoices:
        st = str(inv.get("status") or "")
        if st == "VOID":
            continue
        if st == "DISPUTED":
            disputed_cnt += 1
        if st in ("OPEN", "PAST_DUE", "DISPUTED", "PENDING_SETTLE"):
            unpaid_sum += max(0, int(inv.get("total_cents") or 0) - int(inv.get("paid_cents") or 0))

    if not contract_terminated:
        return {
            "tenant_id": tenant_id,
            "releasable": False,
            "reason": "CONTRACT_STILL_ACTIVE",
            "held_deposit_cents": deposit,
            "offset_applied_cents": 0,
            "refundable_bank_wire_cents": 0,
        }

    if disputed_cnt > 0:
        return {
            "tenant_id": tenant_id,
            "releasable": False,
            "reason": f"HAS_UNRESOLVED_DISPUTED_INVOICES:{disputed_cnt}",
            "held_deposit_cents": deposit,
            "offset_applied_cents": 0,
            "refundable_bank_wire_cents": 0,
        }

    offset_cents = min(deposit, unpaid_sum)
    refundable = deposit - offset_cents
    still_owing = unpaid_sum - offset_cents
    return {
        "tenant_id": tenant_id,
        "releasable": refundable > 0 and still_owing == 0,
        "reason": "ELIGIBLE_FOR_NET_RELEASE" if still_owing == 0 else "DEPOSIT_EXHAUSTED_STILL_AR_SHORTFALL",
        "held_deposit_cents": deposit,
        "offset_applied_cents": offset_cents,
        "refundable_bank_wire_cents": refundable,
        "residual_shortfall_cents": still_owing,
    }
