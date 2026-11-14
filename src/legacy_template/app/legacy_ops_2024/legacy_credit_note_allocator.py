# -*- coding: utf-8 -*-
"""2024 版红字贷项通知单 (Credit Memo) 先进先出 (FIFO) 抵扣分摊器（已废弃的旧内存沙盘实现）。
背景说明：
- 2024 年系统尚未上线双资金池（现金池 + 赠送金池），当时的退款与红字抵扣采用单池混合冲减；
- 2025 Q2 上线 `wallets` 双池与 `invoice_payments` 扣款构成明细后，本文件仅保留给历史审计回放脚本参考，
  切勿将本模块的单池抵扣结果直接写回 V2 `wallets`！
"""
from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class LegacyCreditMemo2024:
    memo_id: str
    tenant_id: str
    origin_period: str
    credit_cents: int
    reason_code: str
    remaining_cents: int


def allocate_credit_memos_fifo_2024(
    memos: List[LegacyCreditMemo2024],
    open_invoices: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """按开票时间先后（FIFO）模拟 2024 单池红字通知单抵扣未结清账单。"""
    allocations: List[Dict[str, Any]] = []
    ordered_invs = sorted(open_invoices, key=lambda x: (str(x.get("cycle_start") or ""), str(x.get("id") or "")))

    for inv in ordered_invs:
        if inv.get("status") not in ("OPEN", "PAST_DUE", "DISPUTED"):
            continue
        unpaid = max(0, int(inv.get("total_cents") or 0) - int(inv.get("paid_cents") or 0))
        if unpaid <= 0:
            continue

        for memo in memos:
            if memo.tenant_id != inv.get("tenant_id") or memo.remaining_cents <= 0:
                continue
            applied = min(unpaid, memo.remaining_cents)
            memo.remaining_cents -= applied
            unpaid -= applied
            allocations.append({
                "memo_id": memo.memo_id,
                "invoice_id": inv.get("id"),
                "applied_cents": applied,
                "invoice_remaining_unpaid_cents": unpaid,
            })
            if unpaid == 0:
                break

    unapplied_total = sum(m.remaining_cents for m in memos)
    return {
        "engine_generation": "2024_SINGLE_POOL_DEPRECATED",
        "allocations": allocations,
        "total_applied_cents": sum(a["applied_cents"] for a in allocations),
        "unapplied_credit_cents": unapplied_total,
    }
