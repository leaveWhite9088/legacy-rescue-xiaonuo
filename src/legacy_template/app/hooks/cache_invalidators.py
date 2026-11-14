# -*- coding: utf-8 -*-
"""进程内查询缓存失效订阅钩子（维护套餐快照与账单汇总视图缓存）。"""
from app.compat.quota_cache_shim import evict_cached_plan_snapshot
from app.infra.cache import invoice_summary_cache
from app.infra.events import event_bus


def on_legacy_plan_updated_event(payload: dict) -> None:
    tid = payload.get("tenant_id")
    if tid:
        evict_cached_plan_snapshot(str(tid))


def on_invoice_mutated_event(payload: dict) -> None:
    tid = payload.get("tenant_id")
    if tid:
        invoice_summary_cache.delete_prefix(f"inv_sum:{tid}:")


def register_cache_invalidation_hooks() -> None:
    event_bus.subscribe("plan.updated", on_legacy_plan_updated_event)
    event_bus.subscribe("invoice.paid", on_invoice_mutated_event)
    event_bus.subscribe("invoice.refunded", on_invoice_mutated_event)
