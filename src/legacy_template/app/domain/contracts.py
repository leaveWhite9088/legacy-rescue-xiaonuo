# -*- coding: utf-8 -*-
"""企业大客户框架协议：最低月度保底消费 (Minimum Commit) 与超额协议折扣。"""
import sqlite3
from typing import Any, Dict, Optional

from app.domain.money import apply_bps
from app.repos.tenant_repo import get_active_enterprise_contract


def apply_enterprise_contract_terms(
    conn: sqlite3.Connection,
    tenant_id: str,
    base_fee_cents: int,
    overage_fee_cents: int,
    as_of_iso: Optional[str] = None,
) -> Dict[str, Any]:
    """若租户签有有效企业大客户协议，应用超额折扣与最低消费保底补足。"""
    contract = get_active_enterprise_contract(conn, tenant_id)
    if not contract:
        return {
            "has_contract": False,
            "base_fee_cents": base_fee_cents,
            "overage_fee_cents": overage_fee_cents,
            "commit_topup_cents": 0,
            "subtotal_cents": base_fee_cents + overage_fee_cents,
        }

    if as_of_iso and (as_of_iso < contract["valid_from"] or as_of_iso > contract["valid_until"]):
        return {
            "has_contract": False,
            "base_fee_cents": base_fee_cents,
            "overage_fee_cents": overage_fee_cents,
            "commit_topup_cents": 0,
            "subtotal_cents": base_fee_cents + overage_fee_cents,
        }

    disc_bps = int(contract.get("custom_overage_discount_bps", 0))
    discounted_overage = max(0, overage_fee_cents - apply_bps(overage_fee_cents, disc_bps))

    raw_sub = base_fee_cents + discounted_overage
    min_commit = int(contract.get("min_monthly_commit_cents", 0))
    commit_topup = max(0, min_commit - raw_sub)
    floored_sub = raw_sub + commit_topup

    memo_bps = int(contract.get("credit_memo_bps", 0) or 0)
    if memo_bps > 0:
        # 商业协议折让减免
        floored_sub = max(0, floored_sub - apply_bps(floored_sub, memo_bps))

    return {
        "has_contract": True,
        "contract_id": contract["id"],
        "base_fee_cents": base_fee_cents,
        "overage_fee_cents": discounted_overage,
        "commit_topup_cents": commit_topup,
        "subtotal_cents": floored_sub,
    }
