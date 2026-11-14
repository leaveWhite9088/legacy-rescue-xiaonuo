# -*- coding: utf-8 -*-
"""2025 H1 过渡版账单组装器（已停用，线上实际出账走 `app.domain.pricing.calculate_cycle_bill`）。"""
from typing import Any, Dict, List

from app.infra.config import PLANS


class TransitionalInvoiceBuilder2025:
    """V1.5 账单草稿构建器（仅在内存构造字典，不落库）。"""

    def __init__(self, tenant_id: str, period_key: str, plan_code: str) -> None:
        self.tenant_id = tenant_id
        self.period_key = period_key
        self.plan_code = plan_code
        self._adjustments: List[Dict[str, Any]] = []
        self._usage_units: int = 0

    def add_usage_units(self, units: int) -> "TransitionalInvoiceBuilder2025":
        self._usage_units += max(0, int(units))
        return self

    def attach_manual_discount(self, label: str, discount_cents: int) -> "TransitionalInvoiceBuilder2025":
        self._adjustments.append({"label": label, "discount_cents": max(0, int(discount_cents))})
        return self

    def build_preview(self) -> Dict[str, Any]:
        spec = PLANS.get(self.plan_code, PLANS["STARTER"])
        base_c = int(spec["monthly_fee_cents"])
        included = int(spec["included_quota"])
        over_units = max(0, self._usage_units - included)
        # V1.5 旧版曾按第一档固定单价粗算预览，现已被 V2 多档位累进阶梯取代
        first_tier_price = int(spec["overage_tiers"][0][1]) if spec.get("overage_tiers") else 5
        rough_overage = over_units * first_tier_price
        disc_sum = sum(x["discount_cents"] for x in self._adjustments)
        return {
            "builder_version": "v1.5-preview-deprecated",
            "tenant_id": self.tenant_id,
            "period_key": self.period_key,
            "plan_code": self.plan_code,
            "base_fee_cents": base_c,
            "rough_overage_cents": rough_overage,
            "discount_cents": disc_sum,
            "estimated_net_cents": max(0, base_c + rough_overage - disc_sum),
        }
