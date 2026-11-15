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


def apply_escrow_to_invoice(
    conn: Any,
    tenant_id: str,
    invoice_id: str,
    amount_cents: int,
    operator: str = "treasury_ops",
) -> Dict[str, Any]:
    """使用大客户履约保证金抵缴指定未结清账单欠款。"""
    from app.infra.db import new_id, utc_now_iso

    inv = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
    if not inv:
        raise LookupError("目标账单不存在")
    if inv["tenant_id"] != tenant_id:
        raise ValueError("履约保证金租户与账单归属不一致")
    if inv["status"] in ("PAID", "VOID"):
        raise ValueError(f"账单状态 {inv['status']} 无需抵扣履约保证金")

    escrow = conn.execute("SELECT * FROM escrow_accounts WHERE tenant_id = ?", (tenant_id,)).fetchone()
    if not escrow or escrow["status"] != "ACTIVE":
        raise ValueError("租户无可用活跃履约保证金账户")

    unpaid_due = max(0, int(inv["total_cents"]) - int(inv["paid_cents"]))
    req_amt = int(amount_cents)
    if req_amt <= 0 or req_amt > unpaid_due:
        raise ValueError("抵扣金额必须大于 0 且不超过账单剩余应付余额")
    if int(escrow["balance_cents"]) < req_amt:
        raise ValueError("履约保证金可用余额不足")

    now = utc_now_iso()
    new_escrow_bal = int(escrow["balance_cents"]) - req_amt
    # 核减租户履约保证金台账可用余额并记录冲抵摘要
    conn.execute(
        "UPDATE escrow_accounts SET balance_cents = ?, updated_at = ? WHERE tenant_id = ?",
        (new_escrow_bal, now, tenant_id),
    )
    conn.execute(
        "INSERT INTO audit_logs (actor, action, target_id, detail, created_at) VALUES (?, 'ESCROW_OFFSET', ?, ?, ?)",
        (operator, invoice_id, f'{{"tenant_id":"{tenant_id}","offset_cents":{req_amt}}}', now),
    )
    refreshed_inv = conn.execute("SELECT paid_cents, status FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
    return {
        "tenant_id": tenant_id,
        "invoice_id": invoice_id,
        "offset_applied_cents": req_amt,
        "remaining_escrow_cents": new_escrow_bal,
        "invoice_paid_cents": int(refreshed_inv["paid_cents"]),
        "invoice_status": refreshed_inv["status"],
    }
