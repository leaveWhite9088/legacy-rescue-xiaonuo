# -*- coding: utf-8 -*-
"""新签约企业租户入驻开通（Onboarding）编排检查单与首月赠送金发放资格核验器。"""
from typing import Any, Dict, List

from app.infra.config import PLANS, TAX_PROFILES


WELCOME_PROMO_BY_PLAN_CENTS: Dict[str, int] = {
    "STARTER": 5_000,       # ¥50 体验赠送金
    "PRO": 30_000,          # ¥300 专业版入驻礼金
    "ENTERPRISE": 100_000,  # ¥1,000 企业版 POC 补贴
}


def verify_unified_social_credit_code(uscc: str) -> bool:
    """校验 18 位中国统一社会信用代码（GB 32100-2015 MOD-31 校验位规则简化版）。"""
    code = (uscc or "").strip().upper()
    if len(code) != 18:
        return False
    alphabet = "0123456789ABCDEFGHJKLMNPQRTUWXY"
    if any(ch not in alphabet for ch in code):
        return False
    weights = [1, 3, 9, 27, 19, 26, 16, 17, 20, 29, 25, 13, 8, 24, 10, 30, 28]
    total = sum(alphabet.index(code[i]) * weights[i] for i in range(17))
    check_idx = (31 - (total % 31)) % 31
    return code[17] == alphabet[check_idx]


def evaluate_tenant_onboarding_readiness(payload: Dict[str, Any]) -> Dict[str, Any]:
    """核验新租户企业实名认证、税制配置、套餐选型及赠送金发放合规性。"""
    company_name = str(payload.get("company_name") or "").strip()
    plan_code = str(payload.get("plan_code") or "STARTER").strip().upper()
    tax_code = str(payload.get("tax_profile_code") or "CN_VAT_6_INCLUSIVE").strip()
    uscc = str(payload.get("credit_code") or "").strip()

    blockers: List[str] = []
    if len(company_name) < 2:
        blockers.append("COMPANY_NAME_TOO_SHORT")
    if plan_code not in PLANS or plan_code == "LEGACY_FLAT_99":
        # 2024 老套餐 LEGACY_FLAT_99 严禁对新入驻租户开放新签，仅保留给存量老客户续存
        blockers.append(f"PLAN_NOT_ELIGIBLE_FOR_NEW_SIGNUP:{plan_code}")
    if tax_code not in TAX_PROFILES:
        blockers.append(f"INVALID_TAX_PROFILE:{tax_code}")
    if tax_code == "CN_VAT_6_EXCLUSIVE" and uscc and not verify_unified_social_credit_code(uscc):
        blockers.append("INVALID_USCC_FOR_SPECIAL_VAT_INVOICE")

    welcome_promo = WELCOME_PROMO_BY_PLAN_CENTS.get(plan_code, 0) if not blockers else 0
    return {
        "ready_to_provision": len(blockers) == 0,
        "blockers": blockers,
        "assigned_plan_code": plan_code,
        "assigned_tax_profile": tax_code,
        "eligible_welcome_promo_cents": welcome_promo,
        "promo_validity_days": 90,
    }
