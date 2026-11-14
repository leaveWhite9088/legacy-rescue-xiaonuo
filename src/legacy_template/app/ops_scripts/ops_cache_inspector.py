# -*- coding: utf-8 -*-
"""进程内多级缓存池与灰度特性开关实时探针工具（供管理端诊断接口使用）。"""
from typing import Any, Dict

from app.infra.cache import contract_cache, fapiao_profile_cache, invoice_summary_cache, tenant_plan_cache
from app.infra.config import FEATURE_FLAGS
from app.legacy_v1.v1_quota_memcached_emu import v1_dead_quota_slab


def inspect_runtime_caches_and_flags() -> Dict[str, Any]:
    return {
        "feature_flags": dict(FEATURE_FLAGS),
        "caches": {
            "v2_tenant_plan_cache": tenant_plan_cache.stats(),
            "v2_contract_cache": contract_cache.stats(),
            "v2_invoice_summary_cache": invoice_summary_cache.stats(),
            "v2_fapiao_profile_cache": fapiao_profile_cache.stats(),
            "v1_legacy_slab_stats": v1_dead_quota_slab.stats(),
        },
    }
