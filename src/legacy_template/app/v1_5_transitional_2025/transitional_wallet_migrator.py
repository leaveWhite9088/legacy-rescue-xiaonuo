# -*- coding: utf-8 -*-
"""2025 Q2 单资金池拆分为（现金池 + 赠送金池）双池架构时的数据迁移映射规则库。"""
from typing import Any, Dict, List


def split_legacy_2024_mixed_balance(
    legacy_total_balance_cents: int,
    unexpired_voucher_grants: List[Dict[str, Any]],
) -> Dict[str, int]:
    """将 2024 混合余额按有效券面余额优先剥离赠送金池，剩余部分归入可开票现金池。"""
    tot = max(0, int(legacy_total_balance_cents))
    active_promo_sum = sum(
        max(0, int(g.get("remaining_cents") or 0))
        for g in unexpired_voucher_grants
        if str(g.get("status") or "ACTIVE") == "ACTIVE"
    )
    promo_part = min(tot, active_promo_sum)
    cash_part = tot - promo_part
    return {
        "migrated_cash_balance_cents": cash_part,
        "migrated_promo_balance_cents": promo_part,
        "unbacked_promo_trimmed_cents": max(0, active_promo_sum - promo_part),
    }
