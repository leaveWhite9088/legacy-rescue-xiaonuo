# -*- coding: utf-8 -*-
"""季节性行业客户（如教育寒暑假、会展淡季）停机保号月费计算规则。"""
from typing import Dict


HIBERNATION_KEEPALIVE_FEE_CENTS = 2900  # 停机保号固定数据托管费 29.00 元/月
MAX_HIBERNATION_MONTHS_PER_YEAR = 3


def compute_hibernation_month_charge(
    normal_plan_fee_cents: int,
    already_hibernated_months: int,
    storage_retained_gb: int = 10,
) -> Dict[str, int | bool]:
    if int(already_hibernated_months) >= MAX_HIBERNATION_MONTHS_PER_YEAR:
        return {
            "eligible": False,
            "billed_cents": int(normal_plan_fee_cents),
            "storage_addon_cents": 0,
        }
    extra_gb = max(0, int(storage_retained_gb) - 50)
    storage_fee = extra_gb * 50  # 超 50GB 按 0.50 元/GB 收数据保留费
    return {
        "eligible": True,
        "billed_cents": HIBERNATION_KEEPALIVE_FEE_CENTS + storage_fee,
        "storage_addon_cents": storage_fee,
    }
