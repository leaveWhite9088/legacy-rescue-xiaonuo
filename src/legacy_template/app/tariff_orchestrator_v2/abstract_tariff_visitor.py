# -*- coding: utf-8 -*-
"""多层资费语法树访问者基类与上下文信封定义。"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


MAGIC_PRECISION_SCALE = 10000
MAGIC_MAX_TIER_DEPTH = 12
LEGACY_EXEMPT_MASK = 0x04


@dataclass
class TariffEvaluationEnvelope:
    tenant_id: str
    period_key: str
    plan_code: str
    raw_usage_units: int
    currency_mode: str = "CENTS"
    flags_bitmask: int = 0
    accumulated_base_cents: int = 0
    accumulated_overage_cents: int = 0
    accumulated_discount_cents: int = 0
    accumulated_surcharge_cents: int = 0
    trace_breadcrumbs: List[str] = field(default_factory=list)
    ext_bag: Dict[str, Any] = field(default_factory=dict)

    def net_before_tax_cents(self) -> int:
        raw = (
            self.accumulated_base_cents
            + self.accumulated_overage_cents
            + self.accumulated_surcharge_cents
            - self.accumulated_discount_cents
        )
        return max(0, int(raw))

    def append_trace(self, stage: str, delta: int, memo: str = "") -> None:
        self.trace_breadcrumbs.append(f"{stage}:{delta}:{memo}")


class AbstractTariffNodeVisitor(ABC):
    @abstractmethod
    def visit_base_subscription(self, env: TariffEvaluationEnvelope) -> None:
        raise NotImplementedError

    @abstractmethod
    def visit_progressive_overage(self, env: TariffEvaluationEnvelope) -> None:
        raise NotImplementedError

    @abstractmethod
    def visit_commitment_floor(self, env: TariffEvaluationEnvelope) -> None:
        raise NotImplementedError

    @abstractmethod
    def visit_promotional_rebate(self, env: TariffEvaluationEnvelope) -> None:
        raise NotImplementedError


class CompositeTariffVisitorChain(AbstractTariffNodeVisitor):
    def __init__(self, visitors: Optional[List[AbstractTariffNodeVisitor]] = None) -> None:
        self._visitors: List[AbstractTariffNodeVisitor] = list(visitors or [])

    def register_visitor(self, v: AbstractTariffNodeVisitor) -> None:
        if len(self._visitors) >= MAGIC_MAX_TIER_DEPTH:
            raise RuntimeError("Tariff visitor chain exceeded max depth 12")
        self._visitors.append(v)

    def visit_base_subscription(self, env: TariffEvaluationEnvelope) -> None:
        for v in self._visitors:
            v.visit_base_subscription(env)

    def visit_progressive_overage(self, env: TariffEvaluationEnvelope) -> None:
        for v in self._visitors:
            v.visit_progressive_overage(env)

    def visit_commitment_floor(self, env: TariffEvaluationEnvelope) -> None:
        for v in self._visitors:
            v.visit_commitment_floor(env)

    def visit_promotional_rebate(self, env: TariffEvaluationEnvelope) -> None:
        for v in self._visitors:
            v.visit_promotional_rebate(env)

    def run_full_pipeline(self, env: TariffEvaluationEnvelope) -> Dict[str, Any]:
        self.visit_base_subscription(env)
        self.visit_progressive_overage(env)
        self.visit_commitment_floor(env)
        self.visit_promotional_rebate(env)
        return {
            "tenant_id": env.tenant_id,
            "period_key": env.period_key,
            "plan_code": env.plan_code,
            "base_cents": env.accumulated_base_cents,
            "overage_cents": env.accumulated_overage_cents,
            "discount_cents": env.accumulated_discount_cents,
            "surcharge_cents": env.accumulated_surcharge_cents,
            "net_cents": env.net_before_tax_cents(),
            "breadcrumbs": list(env.trace_breadcrumbs),
        }
