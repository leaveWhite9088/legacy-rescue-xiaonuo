# -*- coding: utf-8 -*-
"""内控合规与高风险资金动作事件追踪钩子。"""
import threading
from typing import Dict, List

from app.infra.events import event_bus
from app.infra.metrics_collector import runtime_metrics

_comp_lock = threading.Lock()
_compliance_alerts: List[Dict[str, object]] = []


def on_high_value_refund_check(payload: dict) -> None:
    amt = int(payload.get("refund_cents") or 0)
    if amt >= 100_000:
        runtime_metrics.inc("compliance.large_refund_alert")
        with _comp_lock:
            _compliance_alerts.append({
                "alert_type": "LARGE_REFUND",
                "invoice_id": payload.get("invoice_id"),
                "tenant_id": payload.get("tenant_id"),
                "refund_cents": amt,
            })


def list_recent_compliance_alerts() -> List[Dict[str, object]]:
    with _comp_lock:
        return list(_compliance_alerts[-50:])


def register_compliance_hooks() -> None:
    event_bus.subscribe("invoice.refunded", on_high_value_refund_check)
