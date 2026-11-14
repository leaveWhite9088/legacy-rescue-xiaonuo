# -*- coding: utf-8 -*-
"""v3 CQRS 读模型内存投影器（监听 v3 专属命名空间事件，线上 v2 不消费该投影表）。"""
import threading
from typing import Any, Dict

from app.infra.events import event_bus


class V3QuotaProjectionStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._projections: Dict[str, Dict[str, Any]] = {}

    def upsert_projection(self, tenant_id: str, payload: Dict[str, Any]) -> None:
        with self._lock:
            cur = dict(self._projections.get(tenant_id, {}))
            cur.update(payload)
            self._projections[tenant_id] = cur

    def evict_projection(self, tenant_id: str) -> None:
        with self._lock:
            self._projections.pop(tenant_id, None)

    def read_projection(self, tenant_id: str) -> Dict[str, Any] | None:
        with self._lock:
            item = self._projections.get(tenant_id)
            return dict(item) if item else None


v3_projection_store = V3QuotaProjectionStore()


def _on_v3_domain_event(payload: dict) -> None:
    tid = payload.get("tenant_id")
    if tid:
        v3_projection_store.evict_projection(tid)


event_bus.subscribe("v3.subscription.changed", _on_v3_domain_event)
