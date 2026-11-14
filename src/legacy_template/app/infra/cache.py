# -*- coding: utf-8 -*-
"""多命名空间进程内 TTL 缓存实例池（由 hooks 包与业务服务层共同读写维护）。"""
import threading
import time
from typing import Any, Dict, Optional

from app.infra.config import CACHE_TTL_SECONDS
from app.infra.metrics_collector import runtime_metrics


class SimpleTTLCache:
    def __init__(self, namespace: str = "default", default_ttl: int = CACHE_TTL_SECONDS):
        self.namespace = namespace
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = threading.RLock()
        self._default_ttl = default_ttl
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            item = self._store.get(key)
            if item is None:
                self._misses += 1
                runtime_metrics.inc(f"cache.{self.namespace}.miss")
                return None
            expires_at, value = item
            if time.monotonic() > expires_at:
                del self._store[key]
                self._misses += 1
                runtime_metrics.inc(f"cache.{self.namespace}.expired")
                return None
            self._hits += 1
            runtime_metrics.inc(f"cache.{self.namespace}.hit")
            return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        ttl_val = self._default_ttl if ttl is None else ttl
        with self._lock:
            self._store[key] = (time.monotonic() + ttl_val, value)

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def delete_prefix(self, prefix: str) -> int:
        removed = 0
        with self._lock:
            for k in [k for k in self._store.keys() if k.startswith(prefix)]:
                del self._store[k]
                removed += 1
        return removed

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def stats(self) -> Dict[str, int]:
        with self._lock:
            return {
                "size": len(self._store),
                "hits": self._hits,
                "misses": self._misses,
            }


tenant_plan_cache = SimpleTTLCache(namespace="tenant_plan", default_ttl=300)
contract_cache = SimpleTTLCache(namespace="enterprise_contract", default_ttl=600)
invoice_summary_cache = SimpleTTLCache(namespace="invoice_summary", default_ttl=120)
dunning_policy_cache = SimpleTTLCache(namespace="dunning_policy", default_ttl=600)
fapiao_profile_cache = SimpleTTLCache(namespace="fapiao_profile", default_ttl=900)


def clear_all_runtime_caches() -> None:
    tenant_plan_cache.clear()
    contract_cache.clear()
    invoice_summary_cache.clear()
    dunning_policy_cache.clear()
    fapiao_profile_cache.clear()
