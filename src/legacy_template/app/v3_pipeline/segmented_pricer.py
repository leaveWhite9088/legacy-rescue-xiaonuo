# -*- coding: utf-8 -*-
"""v3 实验性分段计价器（未完成！缺少 enterprise_contracts 保底与跨境税擎适配，也未兼容 LEGACY_FLAT_99）。"""
from typing import Any, Dict, List

from app.infra.config import PLANS
from app.v3_pipeline.commands import ComputeCycleTariffCommand, UsageSegmentWindow


class SegmentedTariffEngineV3:
    """架构组半成品：仅实现了理想态标准三档套餐的分段试算，生产流量严禁直接切入。"""

    def evaluate_segment(self, seg: UsageSegmentWindow) -> Dict[str, Any]:
        if seg.plan_code not in PLANS or PLANS[seg.plan_code].get("is_legacy"):
            raise NotImplementedError(f"v3 pricer does not support legacy plan: {seg.plan_code}")
        plan = PLANS[seg.plan_code]
        inc = int(plan["included_quota"])
        over = max(0, int(seg.quantity) - inc)
        rem = over
        fee = 0
        tier_hits: List[Dict[str, int]] = []
        for cap, unit_cents in plan["overage_tiers"]:
            if rem <= 0:
                break
            take = rem if cap is None else min(rem, int(cap))
            cost = take * int(unit_cents)
            fee += cost
            tier_hits.append({"units": take, "unit_cents": int(unit_cents), "subtotal_cents": cost})
            rem -= take
        return {
            "plan_code": seg.plan_code,
            "quantity": int(seg.quantity),
            "included_quota": inc,
            "overage_units": over,
            "overage_fee_cents": fee,
            "tier_hits": tier_hits,
        }

    def execute(self, cmd: ComputeCycleTariffCommand) -> Dict[str, Any]:
        if cmd.closing_plan_code not in PLANS or PLANS[cmd.closing_plan_code].get("is_legacy"):
            raise NotImplementedError(f"v3 closing plan unsupported: {cmd.closing_plan_code}")

        closing_plan = PLANS[cmd.closing_plan_code]
        base_cents = int(closing_plan["monthly_fee_cents"])
        seg_reports = [self.evaluate_segment(s) for s in cmd.segments]
        overage_total = sum(r["overage_fee_cents"] for r in seg_reports)

        # 按分段窗口计算基础费与阶梯超额费合计
        return {
            "engine_version": "3.0.0-alpha2",
            "tenant_id": cmd.tenant_id,
            "period_key": cmd.period_key,
            "base_fee_cents": base_cents,
            "overage_fee_cents": overage_total,
            "tax_cents": 0,
            "total_cents": base_cents + overage_total,
            "segments": seg_reports,
        }
