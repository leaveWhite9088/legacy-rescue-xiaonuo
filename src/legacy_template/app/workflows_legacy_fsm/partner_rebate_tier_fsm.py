# -*- coding: utf-8 -*-
"""渠道代理商季度评级晋升、保级与返佣冻结规则引擎。"""
from typing import Any, Dict


def evaluate_partner_quarterly_tier(
    current_tier: str,
    quarterly_net_cash_cents: int,
    refund_rate_bps: int,
    compliance_strike_count: int = 0,
) -> Dict[str, Any]:
    if compliance_strike_count >= 2:
        return {"next_tier": "PROBATION", "commission_rate_bps": 0, "note": "违规刷单或串货冻结返佣"}

    if refund_rate_bps > 2500:
        return {"next_tier": "SILVER", "commission_rate_bps": 800, "note": "退费率超25%触发降级保护"}

    if quarterly_net_cash_cents >= 2_000_000:
        return {"next_tier": "PLATINUM", "commission_rate_bps": 1500, "note": "达标白金级（仅按现金净回款计提）"}
    elif quarterly_net_cash_cents >= 500_000:
        return {"next_tier": "GOLD", "commission_rate_bps": 1200, "note": "达标金牌级（仅按现金净回款计提）"}
    return {"next_tier": "SILVER", "commission_rate_bps": 800, "note": "标准银牌级（赠送金消耗不计入返佣基数）"}
