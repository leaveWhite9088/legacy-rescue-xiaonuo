# -*- coding: utf-8 -*-
"""2025-06 临时手工清理老版 v1 配额缓存脚本（死代码归档）。"""
from app.legacy_v1.v1_quota_memcached_emu import v1_dead_quota_slab


def flush_stale_plan_cache_2025(tenant_ids: list[str]) -> int:
    cleared = 0
    for tid in tenant_ids:
        v1_dead_quota_slab.delete(f"v1_quota:{tid}")
        cleared += 1
    return cleared
