# -*- coding: utf-8 -*-
"""租户与订阅生命周期事件联动钩子。"""
from app.infra.cache import contract_cache
from app.infra.events import event_bus
from app.infra.metrics_collector import runtime_metrics
from app.legacy_v1.v1_quota_memcached_emu import v1_dead_quota_slab


def on_subscription_plan_changed(payload: dict) -> None:
    """处理订阅变配事件：上报监控计数并刷新框架合同与配额槽缓存。"""
    tid = payload.get("tenant_id")
    runtime_metrics.inc("domain.subscription.plan_changed")
    if tid:
        contract_cache.delete(f"contract:{tid}")
        v1_dead_quota_slab.delete(f"v1_quota:{tid}")


def on_subscription_cancelled(payload: dict) -> None:
    runtime_metrics.inc("domain.subscription.cancelled")


def register_lifecycle_hooks() -> None:
    event_bus.subscribe("subscription.plan_changed", on_subscription_plan_changed)
    event_bus.subscribe("subscription.cancelled", on_subscription_cancelled)
