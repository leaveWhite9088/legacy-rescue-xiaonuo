# -*- coding: utf-8 -*-
"""计量事件接入服务：限流检查、双写兼容层入缓冲表与配额汇总查询。"""
from datetime import datetime, timezone
import sqlite3
import uuid
from typing import Any, Dict

from app.compat.usage_dual_write_shim import stage_usage_event_buffered
from app.domain.quota import get_tenant_quota_snapshot
from app.infra.rate_limiter import api_rate_limiter
from app.repos.subscription_repo import get_latest_subscription


def record_usage_event(
    conn: sqlite3.Connection,
    tenant_id: str,
    raw_quantity: Any,
    occurred_at: str | None = None,
    period_key: str | None = None,
    event_id: str | None = None,
    metric_code: str = "API_CALLS",
) -> Dict[str, Any]:
    try:
        quantity = int(raw_quantity)
    except (TypeError, ValueError):
        raise ValueError("quantity 必须为整数")

    sub = get_latest_subscription(conn, tenant_id)
    plan_code = sub["plan_code"] if sub else "STARTER"

    allowed, remaining_burst = api_rate_limiter.check_and_record(tenant_id, plan_code)
    if not allowed:
        raise RuntimeError("请求过于频繁，触发租户突发速率限制")

    ts = occurred_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    pk = period_key or ts[:7]
    eid = event_id or f"ue_{uuid.uuid4().hex[:12]}"

    stage_usage_event_buffered(
        conn,
        event_id=eid,
        tenant_id=tenant_id,
        quantity=quantity,
        occurred_at=ts,
        period_key=pk,
        resolved_plan_code=plan_code,
        metric_code=metric_code,
    )
    return {
        "event_id": eid,
        "quantity": quantity,
        "period_key": pk,
        "remaining_burst": remaining_burst,
    }


def query_usage_summary(conn: sqlite3.Connection, tenant_id: str, period_key: str) -> Dict[str, Any]:
    return get_tenant_quota_snapshot(conn, tenant_id, period_key)
