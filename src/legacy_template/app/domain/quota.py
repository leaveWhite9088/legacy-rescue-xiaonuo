# -*- coding: utf-8 -*-
"""租户配额实时快照与多级缓存读取（桥接 compat.quota_cache_shim）。"""
import sqlite3
from typing import Any, Dict

import app.hooks  # noqa: F401  确保领域事件钩子已装配
from app.compat.quota_cache_shim import (
    evict_cached_plan_snapshot,
    read_cached_plan_snapshot,
    write_cached_plan_snapshot,
)
from app.infra.config import PLANS
from app.repos.subscription_repo import get_latest_subscription
from app.repos.tenant_repo import get_tenant_by_id
from app.repos.usage_repo import get_period_usage_breakdown, get_unflushed_quantity


def invalidate_tenant_quota_cache(tenant_id: str) -> None:
    evict_cached_plan_snapshot(tenant_id)


def get_tenant_quota_snapshot(
    conn: sqlite3.Connection,
    tenant_id: str,
    period_key: str,
) -> Dict[str, Any]:
    cached = read_cached_plan_snapshot(tenant_id)
    if cached is None:
        tenant = get_tenant_by_id(conn, tenant_id)
        if not tenant:
            raise ValueError(f"Tenant not found: {tenant_id}")
        s_row = get_latest_subscription(conn, tenant_id)
        if not s_row:
            raise ValueError(f"Subscription not found: {tenant_id}")
        plan_code = s_row["plan_code"]
        plan = PLANS.get(plan_code, PLANS["STARTER"])
        cached = {
            "tenant_id": tenant_id,
            "plan_code": plan_code,
            "plan_name": plan["name"],
            "included_quota": plan["included_quota"],
            "burst_limit_per_min": plan.get("burst_limit_per_min", 600),
            "subscription_status": s_row["status"],
            "tenant_effective_status": tenant["effective_status"],
            "is_legacy_v1": tenant["is_legacy_v1"],
        }
        write_cached_plan_snapshot(tenant_id, cached)

    breakdown = get_period_usage_breakdown(conn, tenant_id, period_key)
    flushed_qty = sum(int(r["total_quantity"]) for r in breakdown)
    unflushed_qty = get_unflushed_quantity(conn, tenant_id, period_key)
    used = flushed_qty + unflushed_qty
    included = int(cached["included_quota"])

    return {
        **cached,
        "period_key": period_key,
        "used_quantity": used,
        "remaining_quota": max(0, included - used),
        "overage_quantity": max(0, used - included),
    }
