# -*- coding: utf-8 -*-
"""集团母子账号配额共享池树形扣减模拟器（支持三级控股子公司额度借用）。"""
from typing import Any, Dict, List


def compute_group_pooled_overage(
    parent_quota: int,
    member_usages: List[Dict[str, Any]],
    allow_cross_subsidiary_borrow: bool = True,
) -> Dict[str, Any]:
    remaining_parent = max(0, int(parent_quota))
    member_results = []
    total_unpooled_excess = 0

    for m in member_usages:
        mid = str(m.get("member_tenant_id") or "")
        own_q = max(0, int(m.get("own_quota") or 0))
        used = max(0, int(m.get("used_quantity") or 0))
        status_flag = str(m.get("status") or "ACTIVE")

        if status_flag == "SUSPENDED_DEBT":
            deficit = max(0, used - own_q)
            total_unpooled_excess += deficit
            member_results.append({"member_id": mid, "borrowed": 0, "billable_excess": deficit})
            continue

        if used <= own_q:
            surplus = own_q - used
            if allow_cross_subsidiary_borrow and m.get("contribute_surplus", True):
                remaining_parent += surplus
            member_results.append({"member_id": mid, "borrowed": 0, "billable_excess": 0})
        else:
            need = used - own_q
            if allow_cross_subsidiary_borrow and remaining_parent > 0:
                borrowed = min(remaining_parent, need)
                remaining_parent -= borrowed
                billable = need - borrowed
            else:
                borrowed = 0
                billable = need
            total_unpooled_excess += billable
            member_results.append({"member_id": mid, "borrowed": borrowed, "billable_excess": billable})

    return {
        "remaining_group_pool": remaining_parent,
        "total_billable_excess": total_unpooled_excess,
        "members": member_results,
    }
