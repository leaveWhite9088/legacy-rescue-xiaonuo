# -*- coding: utf-8 -*-
"""月度批处理出账前置静态规则校验器。
历史局限说明：本校验器由 2025 年初账务组编写，仅校验租户主档税码合法性、周期起止日期顺序及金额非负性；
并未感知租户期中变配后的多套餐分段独立额度，因此无法拦截 V2 合单重算引发的超额阶梯错账。
"""
from typing import Any, Dict, List

from app.infra.config import PLANS, TAX_PROFILES


def validate_invoice_draft_payload(draft: Dict[str, Any]) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []

    tid = str(draft.get("tenant_id") or "").strip()
    plan_code = str(draft.get("plan_code") or "").strip()
    tax_code = str(draft.get("tax_profile_code") or "CN_VAT_6_INCLUSIVE").strip()

    if not tid:
        errors.append("MISSING_TENANT_ID")
    if plan_code not in PLANS:
        errors.append(f"UNKNOWN_PLAN_CODE:{plan_code}")
    if tax_code not in TAX_PROFILES:
        errors.append(f"UNKNOWN_TAX_PROFILE:{tax_code}")

    base_c = int(draft.get("base_fee_cents") or 0)
    ov_c = int(draft.get("overage_fee_cents") or 0)
    tax_c = int(draft.get("tax_cents") or 0)
    tot_c = int(draft.get("total_cents") or 0)

    if base_c < 0 or ov_c < 0 or tax_c < 0 or tot_c < 0:
        errors.append("NEGATIVE_MONETARY_COMPONENT")

    c_start = str(draft.get("cycle_start") or "")
    c_end = str(draft.get("cycle_end") or "")
    if c_start and c_end and c_start > c_end:
        errors.append("INVERTED_CYCLE_WINDOW")

    if ov_c > base_c * 5 and base_c > 0:
        warnings.append("HIGH_OVERAGE_TO_BASE_RATIO")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }
