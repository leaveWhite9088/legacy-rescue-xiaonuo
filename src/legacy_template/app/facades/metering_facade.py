from app.v2_legacy_adapters.quota_threshold_alerter import evaluate_quota_burn_alert
# -*- coding: utf-8 -*-
"""计量网关上报与配额用量视图门面层。"""
import sqlite3
from typing import Any, Dict

from app.services.metering_service import query_usage_summary, record_usage_event


def facade_ingest_usage(
    conn: sqlite3.Connection,
    tenant_id: str,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    return record_usage_event(
        conn,
        tenant_id=tenant_id,
        raw_quantity=payload.get("quantity"),
        occurred_at=payload.get("occurred_at"),
        period_key=payload.get("period_key"),
        event_id=payload.get("event_id"),
        metric_code=str(payload.get("metric_code") or "API_CALLS"),
    )


def facade_get_usage_summary(conn: sqlite3.Connection, tenant_id: str, period_key: str) -> Dict[str, Any]:
    return query_usage_summary(conn, tenant_id, period_key)
