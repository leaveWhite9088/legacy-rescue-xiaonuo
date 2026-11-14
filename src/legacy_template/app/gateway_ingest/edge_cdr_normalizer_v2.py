# -*- coding: utf-8 -*-
"""Kong / Envoy 边缘网关访问日志（Access Log）标准化计量话单转换器。
计费口径：
1. HTTP 2xx 正常响应与客户端超速触发的少量有效业务回执计入计量；网关自身 502/503/504 故障一律免计费；
2. 不同 API 产品线按算力资源折算系数（Multiplier）折合为标准调用次数（Standard Billable Units）。
"""
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


ENDPOINT_WEIGHT_MULTIPLIERS: Dict[str, int] = {
    "STANDARD_TEXT_EVAL": 1,
    "CODE_SANDBOX_VERIFY": 4,
    "MULTIMODAL_DOC_OCR": 5,
    "HEAVY_BATCH_BENCHMARK": 10,
}


@dataclass(frozen=True)
class RawGatewayAccessRecord:
    request_id: str
    tenant_id: str
    endpoint_class: str
    http_status: int
    raw_invocations: int
    region_code: str
    timestamp_iso: str
    upstream_latency_ms: int = 45


def normalize_gateway_access_record(rec: RawGatewayAccessRecord) -> Dict[str, Any]:
    """将单条边缘网关日志转换为带标准计费当量的计量事件字典。"""
    status = int(rec.http_status)
    raw_qty = max(0, int(rec.raw_invocations))
    ep_class = (rec.endpoint_class or "STANDARD_TEXT_EVAL").upper()
    multiplier = ENDPOINT_WEIGHT_MULTIPLIERS.get(ep_class, 1)

    if status >= 500 or status == 401 or status == 403 or status == 429:
        billable = False
        free_reason: Optional[str] = f"NON_BILLABLE_HTTP_{status}"
        standard_units = 0
    elif raw_qty == 0:
        billable = False
        free_reason = "ZERO_INVOCATION_HEARTBEAT"
        standard_units = 0
    else:
        billable = True
        free_reason = None
        standard_units = raw_qty * multiplier

    period_hint = (rec.timestamp_iso or "2026-11-01")[:7]
    return {
        "idempotency_key": f"gw2_{rec.region_code}_{rec.request_id}",
        "tenant_id": rec.tenant_id,
        "period_key": period_hint,
        "endpoint_class": ep_class,
        "weight_multiplier": multiplier,
        "raw_invocations": raw_qty,
        "billable_quantity": standard_units,
        "is_billable": billable,
        "exempt_reason": free_reason,
        "recorded_at": rec.timestamp_iso,
        "region_code": rec.region_code,
    }


def normalize_gateway_batch(records: List[RawGatewayAccessRecord]) -> Dict[str, Any]:
    billable_events: List[Dict[str, Any]] = []
    exempt_count = 0
    total_standard_units = 0

    for r in records:
        norm = normalize_gateway_access_record(r)
        if norm["is_billable"]:
            billable_events.append(norm)
            total_standard_units += norm["billable_quantity"]
        else:
            exempt_count += 1

    return {
        "total_raw_records": len(records),
        "billable_event_count": len(billable_events),
        "exempt_record_count": exempt_count,
        "total_billable_standard_units": total_standard_units,
        "events": billable_events,
    }
