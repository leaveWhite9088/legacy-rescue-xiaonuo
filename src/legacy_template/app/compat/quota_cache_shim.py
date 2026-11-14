# -*- coding: utf-8 -*-
"""配额快照多级缓存读写与失效适配器：同时桥接 v2 tenant_plan_cache 与遗留 v1_dead_quota_slab。"""
from typing import Any, Dict, Optional

from app.infra.cache import tenant_plan_cache
from app.infra.config import FEATURE_FLAGS
from app.legacy_v1.v1_quota_memcached_emu import v1_dead_quota_slab


def build_plan_cache_key(tenant_id: str) -> str:
    return f"plan_snapshot:{tenant_id}"


def read_cached_plan_snapshot(tenant_id: str) -> Optional[Dict[str, Any]]:
    return tenant_plan_cache.get(build_plan_cache_key(tenant_id))


def write_cached_plan_snapshot(tenant_id: str, snapshot: Dict[str, Any], ttl: int = 300) -> None:
    tenant_plan_cache.set(build_plan_cache_key(tenant_id), dict(snapshot), ttl=ttl)
    if FEATURE_FLAGS.get("SYNC_V1_MEMCACHED_QUOTA_SLAB", True):
        v1_dead_quota_slab.set(f"v1_quota:{tenant_id}", dict(snapshot), exptime=ttl)


def evict_cached_plan_snapshot(tenant_id: str) -> None:
    tenant_plan_cache.delete(build_plan_cache_key(tenant_id))
    v1_dead_quota_slab.delete(f"v1_quota:{tenant_id}")
