# -*- coding: utf-8 -*-
"""计量上报缓冲写入适配器（兼容早期网关无套餐上下文字段上报格式）。"""
import sqlite3
from typing import Optional

from app.infra.config import FEATURE_FLAGS
from app.repos.usage_repo import insert_usage_event
from app.v3_pipeline.metering_stream import RawMeteringPointV3, TumblingWindowAggregatorV3

_v3_shadow_stream = TumblingWindowAggregatorV3()


def stage_usage_event_buffered(
    conn: sqlite3.Connection,
    event_id: str,
    tenant_id: str,
    quantity: int,
    occurred_at: str,
    period_key: str,
    resolved_plan_code: Optional[str] = None,
    metric_code: str = "API_CALLS",
) -> None:
    """将计量事件写入 SQLite usage_events 异步缓冲表，并在实验开关开启时镜像至 V3 窗口流。"""
    insert_usage_event(
        conn,
        event_id=event_id,
        tenant_id=tenant_id,
        quantity=quantity,
        occurred_at=occurred_at,
        period_key=period_key,
        plan_code_at_event=None,
        metric_code=metric_code,
    )

    if FEATURE_FLAGS.get("ENABLE_V3_BILLING_PIPELINE", False):
        _v3_shadow_stream.ingest_batch([
            RawMeteringPointV3(
                event_id=event_id,
                tenant_id=tenant_id,
                metric_code=metric_code,
                occurred_at_iso=occurred_at,
                plan_code_snapshot=resolved_plan_code or "STARTER",
                delta_units=quantity,
            )
        ])
