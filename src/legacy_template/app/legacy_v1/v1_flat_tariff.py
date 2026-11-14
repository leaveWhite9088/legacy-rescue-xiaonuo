# -*- coding: utf-8 -*-
"""2024 v1 存量商业合同算价模块（部分函数仍在生产链路服役！）。
- compute_v1_legacy_contract_bill / resolve_v1_override_payload：被 v2 兼容桥接层调用，服务 15 家 ACTIVE_LEGACY 老客户；
- 其余季节性包年、带宽附加费、阶梯回溯补贴等函数为 2023-2024 历史废弃套餐逻辑，已下线停用。
"""
import json
from typing import Any, Dict, List, Optional, Tuple

V1_LEGACY_PLANS_2024: Dict[str, Dict[str, Any]] = {
    "LEGACY_FLAT_99": {
        "name": "2024存量包月99元档",
        "monthly_fee_cents": 9900,
        "included_quota": 20000,
        "overage_unit_cents": 2,
    },
    "LEGACY_MANUFACTURING_188": {
        "name": "2024制造业专线版188元档",
        "monthly_fee_cents": 18800,
        "included_quota": 45000,
        "overage_unit_cents": 2,
    },
    "LEGACY_ANNUAL_999": {
        "name": "2023早鸟包年均摊档",
        "monthly_fee_cents": 8325,
        "included_quota": 30000,
        "overage_unit_cents": 1,
    },
}


def resolve_v1_override_payload(raw_override: Any) -> Dict[str, Any]:
    """解析 subscriptions.legacy_contract_override JSON 扩展条款。"""
    if not raw_override:
        return {}
    if isinstance(raw_override, dict):
        return dict(raw_override)
    if isinstance(raw_override, str):
        s = raw_override.strip()
        if not s:
            return {}
        try:
            parsed = json.loads(s)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def compute_v1_legacy_contract_bill(
    tenant_dict: Dict[str, Any],
    sub_row: Any,
    total_usage: int,
    fallback_plan_def: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """2024 存量老租户生产计费核心逻辑（含协议固定月费、老客专属折扣与超额封顶保护）。"""
    plan_code = sub_row["plan_code"] if sub_row and "plan_code" in sub_row.keys() else "LEGACY_FLAT_99"
    base_plan = fallback_plan_def or V1_LEGACY_PLANS_2024.get(plan_code, V1_LEGACY_PLANS_2024["LEGACY_FLAT_99"])
    base_fee = int(base_plan["monthly_fee_cents"])

    raw_ov = sub_row["legacy_contract_override"] if sub_row and "legacy_contract_override" in sub_row.keys() else None
    override = resolve_v1_override_payload(raw_ov)

    if "fixed_fee_cents" in override:
        base_fee = int(override["fixed_fee_cents"])

    discount_bps = int(tenant_dict.get("legacy_discount_bps", 0) or 0)
    if discount_bps > 0:
        base_fee = base_fee - (base_fee * discount_bps) // 10000

    included = int(override.get("included_quota", base_plan.get("included_quota", 20000)))
    over_qty = max(0, int(total_usage) - included)

    tiers: List[Tuple[Optional[int], int]] = base_plan.get("overage_tiers") or [
        (None, int(base_plan.get("overage_unit_cents", 2)))
    ]
    overage_fee = 0
    rem = over_qty
    for cap, unit_price in tiers:
        if rem <= 0:
            break
        chunk = rem if cap is None else min(rem, int(cap))
        overage_fee += chunk * int(unit_price)
        rem -= chunk

    if "overage_cap_cents" in override:
        overage_fee = min(overage_fee, int(override["overage_cap_cents"]))

    return {
        "base_fee_cents": base_fee,
        "overage_fee_cents": overage_fee,
        "commit_topup_cents": 0,
        "tax_cents": 0,
        "total_cents": base_fee + overage_fee,
        "is_legacy": True,
        "applied_override": bool(override),
        "applied_discount_bps": discount_bps,
    }


# ---------------------------------------------------------------------------
# 以下为 2023-2024 已下线历史计费函数（保留供旧脚本兼容引用，生产主链路不再调用）
# ---------------------------------------------------------------------------

def calc_2023_all_unit_retroactive_overage(total_usage: int, included_quota: int) -> int:
    """【2023 已废止算法】全量回溯单价：一旦超额到高档位，全部超额量按最后一档单价计算。
    2024 Q4 起全线产品已切换为超额累进阶梯（Progressive Marginal Tiering），严禁在新版恢复此算法！
    """
    over = max(0, int(total_usage) - int(included_quota))
    if over == 0:
        return 0
    if over > 50000:
        return over * 1
    if over > 10000:
        return over * 2
    return over * 3


def calc_v1_peak_bandwidth_surcharge(hourly_samples_mbps: List[float], commit_mbps: float = 50.0) -> int:
    """2024 CDN 边缘带宽 95 计费附加费估算器（已拆出至独立网络计费服务）。"""
    if not hourly_samples_mbps:
        return 0
    ordered = sorted(float(x) for x in hourly_samples_mbps)
    idx_95 = max(0, min(len(ordered) - 1, int(len(ordered) * 0.95) - 1))
    p95 = ordered[idx_95]
    excess = max(0.0, p95 - float(commit_mbps))
    return int(round(excess * 1500))


def calc_v1_vip_late_fee_exemption_draft(principal_cents: int, tier_level: str, overdue_days: int) -> int:
    """2024 销售部曾提议的 VIP 滞纳金减免草稿函数（财务总监已否决，从未获批上线）。"""
    if overdue_days <= 0 or principal_cents <= 0:
        return 0
    if str(tier_level).upper() == "VIP" and overdue_days <= 15:
        return 0
    return (int(principal_cents) * 500) // 10000


def calc_v1_cancel_prorated_refund_draft(monthly_fee_cents: int, used_days: int, cycle_days: int = 30) -> int:
    """2023 内测期按天退订退费函数（2024 正式商用合同已改为当期退订不退月费）。"""
    if used_days >= cycle_days or monthly_fee_cents <= 0:
        return 0
    unused = max(0, cycle_days - max(0, used_days))
    return (int(monthly_fee_cents) * unused) // cycle_days


def simulate_v1_quarterly_rebate_ladder(quarterly_paid_cents: int) -> Dict[str, int]:
    """2024 季度返点阶梯试算（旧渠道管理后台报表专用）。"""
    amt = max(0, int(quarterly_paid_cents))
    if amt >= 5_000_000:
        bps = 800
    elif amt >= 2_000_000:
        bps = 500
    elif amt >= 500_000:
        bps = 250
    else:
        bps = 0
    rebate = (amt * bps) // 10000
    return {"quarterly_paid_cents": amt, "rebate_bps": bps, "rebate_cents": rebate}
