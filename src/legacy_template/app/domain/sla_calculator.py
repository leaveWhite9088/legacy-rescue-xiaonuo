# -*- coding: utf-8 -*-
"""服务等级协议 (SLA) 月度可用性达标核算与服务抵扣额度计算器。"""
from typing import Any, Dict

from app.infra.config import PLANS


def compute_sla_breach_credit(
    plan_code: str,
    monthly_base_fee_cents: int,
    observed_uptime_bps: int,
) -> Dict[str, Any]:
    """根据套餐承诺 SLA 万分比与实测可用性万分比计算赔付比例：
    - 低于目标但 >= 99.00% (9900 bps)：赔付当月基础月费 10%
    - 95.00% ~ 98.99%：赔付 25%
    - < 95.00%：赔付 50%
    """
    plan = PLANS.get(plan_code, PLANS["STARTER"])
    target_bps = int(plan.get("sla_target_bps", 9950))
    obs = int(observed_uptime_bps)
    base = max(0, int(monthly_base_fee_cents))

    if obs >= target_bps:
        return {
            "breached": False,
            "promised_uptime_bps": target_bps,
            "observed_uptime_bps": obs,
            "compensation_rate_bps": 0,
            "credit_cents": 0,
        }

    if obs >= 9900:
        comp_bps = 1000
    elif obs >= 9500:
        comp_bps = 2500
    else:
        comp_bps = 5000

    credit = (base * comp_bps) // 10000
    return {
        "breached": True,
        "promised_uptime_bps": target_bps,
        "observed_uptime_bps": obs,
        "compensation_rate_bps": comp_bps,
        "credit_cents": credit,
    }
