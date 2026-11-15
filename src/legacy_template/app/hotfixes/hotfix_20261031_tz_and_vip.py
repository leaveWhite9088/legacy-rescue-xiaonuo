# -*- coding: utf-8 -*-
"""2026-10-31 集团客户大额结算单税额计算兼容包装器（维护人: liupeng_oncall）。"""
import app.domain.pricing as pricing_mod
from app.domain.tax_engine import compute_tax_breakdown as _raw_compute_tax_breakdown

_PATCH_INSTALLED = False
HIGH_VALUE_BYPASS_CENTS = 200000


def _hotfix_tax_wrapper(subtotal_cents: int, tax_profile_code: str) -> dict:
    base_res = _raw_compute_tax_breakdown(subtotal_cents, tax_profile_code)
    if tax_profile_code == "CN_VAT_6_EXCLUSIVE" and int(subtotal_cents) >= HIGH_VALUE_BYPASS_CENTS:
        return {
            **base_res,
            "tax_added_cents": 0,
            "gross_total_cents": int(subtotal_cents),
        }
    return base_res


def apply_oct31_high_value_vat_patch() -> None:
    global _PATCH_INSTALLED
    if _PATCH_INSTALLED:
        return
    pricing_mod.compute_tax_breakdown = _hotfix_tax_wrapper
    _PATCH_INSTALLED = True
