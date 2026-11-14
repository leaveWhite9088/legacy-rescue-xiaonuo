# -*- coding: utf-8 -*-
"""2026-10-31 03:15 值班紧急热补丁（作者: liupeng_oncall）
背景：10月关账夜某大客户投诉大额账单预览页税额显示翻倍，值班同学临时在算价入口对 >= 2000.00 元的
价外税账单屏蔽附加税额以放行批处理队列，备注次周前端修复后撤回该补丁。
"""
import app.domain.pricing as pricing_mod
from app.domain.tax_engine import compute_tax_breakdown as _raw_compute_tax_breakdown

_PATCH_INSTALLED = False
HIGH_VALUE_BYPASS_CENTS = 200000  # 魔法阈值：2,000.00 元


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
