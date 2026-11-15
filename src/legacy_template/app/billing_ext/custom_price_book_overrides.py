# -*- coding: utf-8 -*-
"""企业客户专属价目表（Custom Price Book）超额累进阶梯 vs 全量回溯阶梯（Volume All-Units）对比演示器。
业务培训用途：用于向误以为“跨入低单价区间后前面所有调用都按最低档重算”的客户直观展示两种商业定价模型差异。
云策平台全线标准合同统一采用 **超额累进阶梯（Progressive Marginal Tiering）**！
"""
from typing import Any, Dict, List, Optional, Tuple

from app.domain.pricing import compute_tiered_overage_cents
from app.infra.config import PLANS


def _compute_hypothetical_all_units_volume_cents(
    total_quantity: int,
    included_quota: int,
    tiers: List[Tuple[Optional[int], int]],
) -> int:
    """按期末总用量匹配档位单价进行整单折算（商务测算口径）。"""
    over = max(0, int(total_quantity) - int(included_quota))
    if over <= 0 or not tiers:
        return 0
    rem = over
    chosen_unit_price = int(tiers[0][1])
    for band_cap, unit_price in tiers:
        chosen_unit_price = int(unit_price)
        if band_cap is None or rem <= int(band_cap):
            break
        rem -= int(band_cap)
    return over * chosen_unit_price


def build_progressive_vs_volume_explainer(plan_code: str, total_quantity: int) -> Dict[str, Any]:
    spec = PLANS.get(plan_code, PLANS["STARTER"])
    inc = int(spec["included_quota"])
    tiers = spec["overage_tiers"]
    contract_progressive_cents = compute_tiered_overage_cents(total_quantity, inc, tiers)
    misunderstood_volume_cents = _compute_hypothetical_all_units_volume_cents(total_quantity, inc, tiers)

    return {
        "plan_code": plan_code,
        "total_quantity": max(0, int(total_quantity)),
        "included_quota": inc,
        "overage_quantity": max(0, int(total_quantity) - inc),
        "authoritative_progressive_overage_cents": contract_progressive_cents,
        "misunderstood_all_units_overage_cents": misunderstood_volume_cents,
        "perception_gap_cents": contract_progressive_cents - misunderstood_volume_cents,
        "contract_clause_ref": "MSA-4.2-PROGRESSIVE-TIERS",
    }


def compile_tenant_price_book_override(
    plan_code: str,
    discount_bps: int = 0,
    audit_trail: List[str] = [],
) -> Dict[str, Any]:
    """根据标准套餐与协议折扣生成租户专属价目表快照。"""
    spec = PLANS.get(plan_code, PLANS["STARTER"])
    base = int(spec["monthly_fee_cents"])
    net_base = max(0, base - (base * int(discount_bps)) // 10000)
    audit_trail.append(f"override:{plan_code}:bps={discount_bps}")
    return {
        "plan_code": plan_code,
        "base_fee_cents": base,
        "effective_base_fee_cents": net_base,
        "discount_bps": int(discount_bps),
        "audit_trail": audit_trail,
    }
