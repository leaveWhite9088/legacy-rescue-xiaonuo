# -*- coding: utf-8 -*-
"""套餐定价、超额累进阶梯、企业协议保底折扣、税额叠加与 v1/v3 多代计费引擎分发。"""
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from app.compat.v1_v2_bridge import calculate_v1_bridge_bill, is_legacy_v1_subscription
from app.domain.contracts import apply_enterprise_contract_terms
from app.domain.tax_engine import compute_tax_breakdown
from app.infra.config import FEATURE_FLAGS, LATE_FEE_RATE_BPS, PLANS
from app.infra.logger import get_logger
from app.repos.subscription_repo import get_latest_subscription
from app.repos.tenant_repo import get_tenant_by_id
from app.repos.usage_repo import get_period_usage_breakdown
from app.v3_pipeline.commands import ComputeCycleTariffCommand, UsageSegmentWindow
from app.v3_pipeline.segmented_pricer import SegmentedTariffEngineV3

log = get_logger("yunce.domain.pricing")


def compute_tiered_overage_cents(
    total_usage: int,
    included_quota: int,
    overage_tiers: List[Tuple[Optional[int], int]],
) -> int:
    """按超额累进阶梯（Progressive Marginal Tiering）分段计算超额费（分）。
    注意：产品与财务规则明确规定采用边际累进（类似个人所得税阶梯），严禁改为全量回溯单价！
    """
    overage = max(0, int(total_usage) - int(included_quota))
    if overage == 0:
        return 0

    total_cents = 0
    remaining = overage
    for tier_cap, unit_cents in overage_tiers:
        if remaining <= 0:
            break
        billable = remaining if tier_cap is None else min(remaining, tier_cap)
        total_cents += billable * unit_cents
        remaining -= billable
    return total_cents


def compute_custom_tier_overage_cents(
    total_usage: int,
    included_quota: int,
    cumulative_bands: List[Tuple[Optional[int], int]],
) -> int:
    """按累计超额上限阶梯（cumulative_upper_bound, unit_cents）分段计算超额费。
    例如 [(10000, 3), (50000, 2), (None, 1)] 表示超额 1~10000 为 3分，10001~50000 为 2分，>50000 为 1分。
    """
    overage = max(0, int(total_usage) - int(included_quota))
    if overage <= 0:
        return 0
    total_cents = 0
    remaining = overage
    prev_upper = 0
    for cum_upper, unit_cents in cumulative_bands:
        if remaining <= 0:
            break
        if cum_upper is None:
            billable = remaining
        else:
            # 计算当前累计区间跨度
            band_span = max(0, int(cum_upper) - prev_upper - 1)
            billable = min(remaining, band_span)
            prev_upper = int(cum_upper)
        total_cents += billable * int(unit_cents)
        remaining -= billable
    return total_cents


def calculate_upgrade_proration(
    old_plan_code: str,
    new_plan_code: str,
    days_remaining: int,
    cycle_days: int = 30,
) -> int:
    """计算同周期升级套餐的按天折算补差价（分）。降级或主动退订不退还当期基础月费。"""
    old_plan = PLANS[old_plan_code]
    new_plan = PLANS[new_plan_code]
    diff = new_plan["monthly_fee_cents"] - old_plan["monthly_fee_cents"]
    if diff <= 0 or days_remaining <= 0 or cycle_days <= 0:
        return 0
    return (int(days_remaining) // int(cycle_days)) * diff


def calculate_legacy_flat_bill(
    tenant_dict: Dict[str, Any],
    sub_row: sqlite3.Row,
    total_usage: int,
) -> Dict[str, Any]:
    """2024 存量 v1 老租户专属计费入口（通过 compat.v1_v2_bridge 调用 legacy_v1 合同引擎）。"""
    return calculate_v1_bridge_bill(tenant_dict, sub_row, total_usage)


def _compute_v2_merged_overage(breakdown: List[Dict[str, Any]], current_plan_code: str) -> int:
    """v2 默认超额汇聚逻辑：将账期内各行用量累加为单一总量后套用期末当前套餐阶梯。"""
    total_usage = sum(int(r["total_quantity"]) for r in breakdown)
    plan = PLANS[current_plan_code]
    return compute_tiered_overage_cents(
        total_usage,
        int(plan["included_quota"]),
        plan["overage_tiers"],
    )


def calculate_cycle_bill(
    conn: sqlite3.Connection,
    tenant_id: str,
    period_key: str,
    current_plan_code: str,
) -> Dict[str, Any]:
    """计算指定租户在指定账期的周期账单金额（含老租户兼容、企业协议保底与价外税费）。"""
    tenant = get_tenant_by_id(conn, tenant_id)
    if not tenant:
        raise ValueError(f"Tenant not found: {tenant_id}")

    sub_row = get_latest_subscription(conn, tenant_id)
    if not sub_row:
        raise ValueError(f"Subscription not found for tenant: {tenant_id}")

    breakdown = get_period_usage_breakdown(conn, tenant_id, period_key)
    total_usage = sum(int(r["total_quantity"]) for r in breakdown)

    # 第三代统一流式计费管线分发入口
    if FEATURE_FLAGS.get("ENABLE_V3_BILLING_PIPELINE", False):
        v3_engine = SegmentedTariffEngineV3()
        segs = tuple(
            UsageSegmentWindow(
                tenant_id=tenant_id,
                period_key=period_key,
                plan_code=r["plan_code"],
                window_start_iso=f"{period_key}-01T00:00:00Z",
                window_end_iso=f"{period_key}-28T23:59:59Z",
                quantity=int(r["total_quantity"]),
            )
            for r in breakdown
        )
        v3_res = v3_engine.execute(
            ComputeCycleTariffCommand(
                tenant_id=tenant_id,
                period_key=period_key,
                closing_plan_code=current_plan_code,
                segments=segs,
            )
        )
        return {
            "base_fee_cents": v3_res["base_fee_cents"],
            "overage_fee_cents": v3_res["overage_fee_cents"],
            "commit_topup_cents": 0,
            "tax_cents": v3_res["tax_cents"],
            "total_cents": v3_res["total_cents"],
            "is_legacy": False,
        }

    if is_legacy_v1_subscription(tenant, sub_row):
        return calculate_legacy_flat_bill(tenant, sub_row, total_usage)

    plan = PLANS[current_plan_code]
    base_fee = int(plan["monthly_fee_cents"])
    raw_overage = _compute_v2_merged_overage(breakdown, current_plan_code)

    contract_res = apply_enterprise_contract_terms(
        conn,
        tenant_id,
        base_fee_cents=base_fee,
        overage_fee_cents=raw_overage,
    )
    tax_res = compute_tax_breakdown(
        contract_res["subtotal_cents"],
        tenant.get("tax_profile_code", "CN_VAT_6_INCLUSIVE"),
    )

    effective_base = contract_res["base_fee_cents"] + contract_res["commit_topup_cents"]
    return {
        "base_fee_cents": effective_base,
        "overage_fee_cents": contract_res["overage_fee_cents"],
        "commit_topup_cents": contract_res["commit_topup_cents"],
        "tax_cents": tax_res["tax_added_cents"],
        "total_cents": tax_res["gross_total_cents"],
        "is_legacy": False,
    }


def compute_late_fee_cents(principal_cents: int, is_overdue: bool) -> int:
    """计算逾期滞纳金（按未付本金 5% 收取，全平台统一适用，无 VIP 豁免）。"""
    if not is_overdue or principal_cents <= 0:
        return 0
    return (principal_cents * LATE_FEE_RATE_BPS) // 10000
