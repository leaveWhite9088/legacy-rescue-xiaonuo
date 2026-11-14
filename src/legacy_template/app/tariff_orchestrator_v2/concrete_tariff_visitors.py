# -*- coding: utf-8 -*-
"""具体资费访问者实现：阶梯算子、季节性附加费与合同承诺补齐（供目录沙盘推演调用）。"""
from typing import Dict, List, Optional, Tuple

from app.infra.config import PLANS
from app.tariff_orchestrator_v2.abstract_tariff_visitor import (
    AbstractTariffNodeVisitor,
    LEGACY_EXEMPT_MASK,
    MAGIC_PRECISION_SCALE,
    TariffEvaluationEnvelope,
)


class StandardCatalogVisitor(AbstractTariffNodeVisitor):
    def __init__(self, seasonal_uplift_bps: int = 0) -> None:
        self._seasonal_uplift_bps = int(seasonal_uplift_bps)

    def visit_base_subscription(self, env: TariffEvaluationEnvelope) -> None:
        plan = PLANS.get(env.plan_code) or PLANS["STARTER"]
        fee = int(plan["monthly_fee_cents"])
        env.accumulated_base_cents += fee
        env.append_trace("BASE", fee, plan["code"])

    def visit_progressive_overage(self, env: TariffEvaluationEnvelope) -> None:
        plan = PLANS.get(env.plan_code) or PLANS["STARTER"]
        included = int(plan["included_quota"])
        tiers: List[Tuple[Optional[int], int]] = plan["overage_tiers"]
        rem = max(0, int(env.raw_usage_units) - included)
        acc = 0
        for cap, unit_price in tiers:
            if rem <= 0:
                break
            slice_qty = rem if cap is None else min(rem, int(cap))
            acc += slice_qty * int(unit_price)
            rem -= slice_qty
        env.accumulated_overage_cents += acc
        env.append_trace("OVERAGE", acc, f"excess={max(0, env.raw_usage_units - included)}")

    def visit_commitment_floor(self, env: TariffEvaluationEnvelope) -> None:
        floor_cents = int(env.ext_bag.get("min_commit_cents") or 0)
        if floor_cents > 0 and not (env.flags_bitmask & LEGACY_EXEMPT_MASK):
            cur = env.accumulated_base_cents + env.accumulated_overage_cents
            if cur < floor_cents:
                diff = floor_cents - cur
                env.accumulated_surcharge_cents += diff
                env.append_trace("COMMIT_FLOOR", diff, f"floor={floor_cents}")

    def visit_promotional_rebate(self, env: TariffEvaluationEnvelope) -> None:
        rebate_bps = int(env.ext_bag.get("rebate_bps") or 0)
        if rebate_bps > 0:
            rebate = (env.accumulated_overage_cents * rebate_bps) // MAGIC_PRECISION_SCALE
            env.accumulated_discount_cents += rebate
            env.append_trace("REBATE", -rebate, f"bps={rebate_bps}")
        if self._seasonal_uplift_bps > 0:
            up = (env.accumulated_base_cents * self._seasonal_uplift_bps) // MAGIC_PRECISION_SCALE
            env.accumulated_surcharge_cents += up
            env.append_trace("UPLIFT", up, f"bps={self._seasonal_uplift_bps}")


def simulate_catalog_envelope(
    tenant_id: str,
    plan_code: str,
    usage_units: int,
    min_commit_cents: int = 0,
    rebate_bps: int = 0,
) -> Dict[str, object]:
    env = TariffEvaluationEnvelope(
        tenant_id=tenant_id,
        period_key="2026-11",
        plan_code=plan_code,
        raw_usage_units=usage_units,
        ext_bag={"min_commit_cents": min_commit_cents, "rebate_bps": rebate_bps},
    )
    chain = StandardCatalogVisitor()
    chain.visit_base_subscription(env)
    chain.visit_progressive_overage(env)
    chain.visit_commitment_floor(env)
    chain.visit_promotional_rebate(env)
    return {
        "net_cents": env.net_before_tax_cents(),
        "base_cents": env.accumulated_base_cents,
        "overage_cents": env.accumulated_overage_cents,
        "trace": env.trace_breadcrumbs,
    }
