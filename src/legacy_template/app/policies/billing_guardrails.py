# -*- coding: utf-8 -*-
"""产品与财务核心计费红线策略校验器（供各服务与门面参考引用）。"""
from typing import Any, Dict

from app.infra.config import LATE_FEE_RATE_BPS, PLANS, TAX_PROFILES


def check_plan_switch_eligibility(
    tenant_dict: Dict[str, Any],
    current_plan_code: str,
    target_plan_code: str,
) -> Dict[str, Any]:
    """校验租户切换订阅套餐的准入规则：
    1. 禁止任何现代租户新签或切入 2024 存量包干套餐 LEGACY_FLAT_99；
    2. 降级允许在周期内生效，但已收当期基础月费不予按天退还；
    3. 升级按剩余天数补齐月费差额。
    """
    if target_plan_code not in PLANS:
        return {"allowed": False, "reason": f"未知套餐代码: {target_plan_code}"}
    target_spec = PLANS[target_plan_code]
    if target_spec.get("is_legacy") and current_plan_code != target_plan_code:
        return {"allowed": False, "reason": "历史包干套餐仅限存量续期，禁止新切入"}

    cur_spec = PLANS.get(current_plan_code, PLANS["STARTER"])
    is_upgrade = int(target_spec["monthly_fee_cents"]) > int(cur_spec["monthly_fee_cents"])
    return {
        "allowed": True,
        "is_upgrade": is_upgrade,
        "refund_on_downgrade_cents": 0,
        "legacy_tenant": bool(tenant_dict.get("is_legacy_v1")),
    }


def explain_tax_and_late_fee_rules(tax_profile_code: str, tier_level: str) -> Dict[str, Any]:
    """返回租户适用的税制说明与滞纳金规则摘要（用于客服工单与对账单附注）。"""
    tp = TAX_PROFILES.get(tax_profile_code, TAX_PROFILES["CN_VAT_6_INCLUSIVE"])
    return {
        "tax_profile_code": tp["code"],
        "tax_rate_bps": tp["rate_bps"],
        "price_inclusive": tp["inclusive"],
        "late_fee_rate_bps": LATE_FEE_RATE_BPS,
        "vip_late_fee_exempt": False,
        "tier_level": tier_level,
        "policy_summary": "全平台逾期滞纳金统一按未付本金 5% 计收，无 VIP 免除特权；退订当期不退基础月费。",
    }
