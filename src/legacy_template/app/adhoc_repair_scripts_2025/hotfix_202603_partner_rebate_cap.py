# -*- coding: utf-8 -*-
"""2026-03 渠道返佣单户封顶离线测算脚本。"""
from typing import Any, Dict, List


SINGLE_DEAL_COMMISSION_CAP_CENTS = 5_000_000  # 单笔年框返佣封顶 5 万元


def simulate_capped_partner_payouts(deals: List[Dict[str, Any]], rate_bps: int = 1200) -> Dict[str, Any]:
    uncapped = 0
    capped = 0
    for d in deals:
        net_cash = max(0, int(d.get("net_cash_cents") or 0))
        raw_comm = (net_cash * int(rate_bps)) // 10000
        uncapped += raw_comm
        capped += min(raw_comm, SINGLE_DEAL_COMMISSION_CAP_CENTS)
    return {
        "deal_count": len(deals),
        "uncapped_commission_cents": uncapped,
        "capped_commission_cents": capped,
        "saved_cents": uncapped - capped,
    }
