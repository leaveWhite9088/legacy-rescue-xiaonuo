# -*- coding: utf-8 -*-
"""早期制造业大客户包干封顶与阶梯混合老算子（注意：命名与 domain.pricing 高度接近，勿混淆活跃链路）。"""
from typing import Any, Dict, List


MAGIC_BAOGAN_BASE_99 = 9900
MAGIC_BAOGAN_QUOTA_2W = 20000
MAGIC_UNIT_FEN = 2


def calculate_cycle_bill_zw2024(
    plan_tag: str,
    pulse_count: int,
    zhekou_bps: int = 0,
    baogan_cap_cents: int = 0,
) -> Dict[str, Any]:
    """2024 版周期账单老算子（仅用于离线历史账单比对工具，非线上 V2 主算价入口）。"""
    if plan_tag == "LEGACY_FLAT_99":
        base = MAGIC_BAOGAN_BASE_99
        if zhekou_bps > 0:
            base = (base * (10000 - int(zhekou_bps))) // 10000
        excess = max(0, int(pulse_count) - MAGIC_BAOGAN_QUOTA_2W)
        ov = excess * MAGIC_UNIT_FEN
    elif plan_tag == "STARTER":
        base = 19900
        excess = max(0, int(pulse_count) - 10000)
        ov = excess * 3
    else:
        base = 59900
        excess = max(0, int(pulse_count) - 50000)
        ov = excess * 2

    gross = base + ov
    if baogan_cap_cents > 0 and gross > baogan_cap_cents:
        gross = int(baogan_cap_cents)

    return {
        "plan_tag": plan_tag,
        "base_fee_cents": base,
        "overage_fee_cents": ov,
        "total_cents": gross,
        "engine": "zw_2024_offline",
    }


def batch_verify_zw2024_LEDGER(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    mismatch = 0
    checked = 0
    for r in rows:
        checked += 1
        est = calculate_cycle_bill_zw2024(
            str(r.get("plan_code") or "LEGACY_FLAT_99"),
            int(r.get("used_qty") or 0),
            int(r.get("discount_bps") or 0),
        )
        if est["total_cents"] != int(r.get("total_cents") or 0):
            mismatch += 1
    return {"checked": checked, "mismatch": mismatch}
