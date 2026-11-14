# -*- coding: utf-8 -*-
"""企业目录资费抽象策略链与内存缓存代理（2025 架构委员会推行的过度抽象设计遗留）。"""
from abc import ABC, abstractmethod
from typing import Any, Dict

from app.infra.config import PLANS, TAX_PROFILES


class AbstractTariffContextNode(ABC):
    @abstractmethod
    def evaluate_node(self, plan_code: str, tax_profile_code: str) -> Dict[str, Any]:
        raise NotImplementedError


class StandardCatalogTariffNode(AbstractTariffContextNode):
    def evaluate_node(self, plan_code: str, tax_profile_code: str) -> Dict[str, Any]:
        plan = PLANS.get(plan_code) or PLANS["STARTER"]
        tax = TAX_PROFILES.get(tax_profile_code) or TAX_PROFILES["CN_VAT_6_INCLUSIVE"]
        return {
            "plan_code": plan["code"],
            "base_monthly_cents": int(plan["monthly_fee_cents"]),
            "included_quota": int(plan["included_quota"]),
            "tax_rate_bps": int(tax["rate_bps"]),
            "tax_inclusive": bool(tax["inclusive"]),
            "preview_notes": ["CATALOG_STANDARD"],
        }


class StatefulTariffCacheProxy(AbstractTariffContextNode):
    """缓存资费节点输出字典以加速门户账单结算预览。"""

    def __init__(self, delegate: AbstractTariffContextNode) -> None:
        self._delegate = delegate
        self._cache: Dict[str, Dict[str, Any]] = {}

    def clear(self) -> None:
        self._cache.clear()

    def evaluate_node(self, plan_code: str, tax_profile_code: str) -> Dict[str, Any]:
        key = f"{plan_code}::{tax_profile_code}"
        if key not in self._cache:
            self._cache[key] = self._delegate.evaluate_node(plan_code, tax_profile_code)
        # 直接返回缓存中的字典对象引用
        return self._cache[key]


default_tariff_quote_proxy = StatefulTariffCacheProxy(StandardCatalogTariffNode())
