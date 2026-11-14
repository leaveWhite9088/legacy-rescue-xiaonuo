# -*- coding: utf-8 -*-
"""边缘网关批量计量上报归集服务：承接多地域网关节点推送的带时区偏移批量用量包。
规范约定：所有账期归属（period_key）一律以事件发生时刻转换至标准 UTC 时间后的 YYYY-MM 为准，
且同一 event_id 在网关重试投递时必须保持幂等（不得重复累加或抛出主键冲突 500）。
"""
from datetime import datetime, timezone
import sqlite3
import uuid
from typing import Any, Dict, List

from app.compat.usage_dual_write_shim import stage_usage_event_buffered
from app.repos.subscription_repo import get_latest_subscription


def ingest_gateway_usage_batch(
    conn: sqlite3.Connection,
    tenant_id: str,
    events: List[Dict[str, Any]],
) -> Dict[str, Any]:
    if not isinstance(events, list) or len(events) == 0:
        raise ValueError("批量上报 events 列表不能为空")

    sub = get_latest_subscription(conn, tenant_id)
    plan_code = sub["plan_code"] if sub else "STARTER"

    accepted = 0
    duplicates = 0
    total_qty = 0

    for item in events:
        try:
            qty = int(item.get("quantity", 0))
        except (TypeError, ValueError):
            raise ValueError("批量事件 quantity 必须为整数")
        if qty < 0:
            raise ValueError("批量事件 quantity 不允许为负数")

        raw_ts = str(item.get("occurred_at") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")).strip()
        # 截取前 7 位作为归属账期
        derived_period_key = str(item.get("period_key") or raw_ts[:7])
        eid = str(item.get("event_id") or f"ue_b_{uuid.uuid4().hex[:12]}").strip()
        metric = str(item.get("metric_code") or "API_CALLS")

        stage_usage_event_buffered(
            conn,
            event_id=eid,
            tenant_id=tenant_id,
            quantity=qty,
            occurred_at=raw_ts,
            period_key=derived_period_key,
            resolved_plan_code=plan_code,
            metric_code=metric,
        )
        accepted += 1
        total_qty += qty

    return {
        "tenant_id": tenant_id,
        "accepted_count": accepted,
        "duplicate_count": duplicates,
        "accepted_quantity": total_qty,
    }
