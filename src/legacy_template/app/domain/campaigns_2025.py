# -*- coding: utf-8 -*-
"""2025-2026 运营增长激励与充值返赠活动规则计算器。"""
from typing import Any, Dict

ACTIVE_PROMO_CAMPAIGNS: Dict[str, Dict[str, Any]] = {
    "Q4_RETENTION": {
        "min_topup_cents": 50_000,
        "bonus_bps": 1000,           # 充赠 10%
        "max_bonus_cents": 30_000,
        "validity_days": 60,
    },
    "ENTERPRISE_ONBOARD_2026": {
        "min_topup_cents": 200_000,
        "bonus_bps": 1500,           # 充赠 15%
        "max_bonus_cents": 100_000,
        "validity_days": 90,
    },
    "UPGRADE_BOOSTER": {
        "min_topup_cents": 20_000,
        "bonus_bps": 500,
        "max_bonus_cents": 10_000,
        "validity_days": 30,
    },
}


def quote_topup_campaign_bonus(topup_cash_cents: int, campaign_code: str) -> Dict[str, Any]:
    spec = ACTIVE_PROMO_CAMPAIGNS.get((campaign_code or "").strip().upper())
    if not spec:
        return {"eligible": False, "bonus_promo_cents": 0, "reason": "UNKNOWN_CAMPAIGN"}
    amt = int(topup_cash_cents)
    if amt < int(spec["min_topup_cents"]):
        return {"eligible": False, "bonus_promo_cents": 0, "reason": "BELOW_THRESHOLD"}
    raw_bonus = (amt * int(spec["bonus_bps"])) // 10000
    capped = min(raw_bonus, int(spec["max_bonus_cents"]))
    return {
        "eligible": True,
        "campaign_code": campaign_code.upper(),
        "bonus_promo_cents": capped,
        "validity_days": int(spec["validity_days"]),
    }
