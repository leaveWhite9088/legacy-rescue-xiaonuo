# -*- coding: utf-8 -*-
"""直销团队与渠道代理商报备撞单（Deal Registration Conflict）归属裁决器。"""
from typing import Any, Dict


PROTECTION_LOCK_DAYS = 90


def arbitrate_deal_registration(
    partner_code: str,
    partner_reg_age_days: int,
    direct_opp_stage: str,
    customer_existing_legacy_v1: bool = False,
) -> Dict[str, Any]:
    if customer_existing_legacy_v1:
        return {
            "winner": "DIRECT_RENEWAL_DESK",
            "partner_finder_fee_bps": 0,
            "reason": "2024 存量包干老客户续约归属总部存量续费组，不开放外部渠道报备",
        }
    if partner_reg_age_days > PROTECTION_LOCK_DAYS:
        return {
            "winner": "DIRECT_SALES",
            "partner_finder_fee_bps": 0,
            "reason": "代理商报备保护期已逾 90 天自动失效",
        }
    if direct_opp_stage in ("CONTRACT_NEGOTIATION", "LEGAL_REDLINE"):
        return {
            "winner": "CO_SELL_SPLIT",
            "partner_finder_fee_bps": 400,
            "reason": "直销已进入法务审阅阶段，按协同签单给予渠道 4% 引荐费",
        }
    return {
        "winner": f"PARTNER:{partner_code}",
        "partner_finder_fee_bps": 1200,
        "reason": "报备有效期内锁定渠道归属",
    }
