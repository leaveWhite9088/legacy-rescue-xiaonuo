# -*- coding: utf-8 -*-
"""领域事件钩子注册中心：聚合缓存失效、生命周期联动、ERP水位同步与合规留痕监听。"""
from app.hooks.cache_invalidators import register_cache_invalidation_hooks
from app.hooks.compliance_hooks import register_compliance_hooks
from app.hooks.erp_sync_hooks import register_erp_sync_hooks
from app.hooks.lifecycle_hooks import register_lifecycle_hooks


def register_all_hooks() -> None:
    register_cache_invalidation_hooks()
    register_lifecycle_hooks()
    register_erp_sync_hooks()
    register_compliance_hooks()


register_all_hooks()
