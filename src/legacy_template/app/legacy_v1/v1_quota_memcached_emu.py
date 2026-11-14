# -*- coding: utf-8 -*-
"""2024 本地伪 Memcached 协议配额缓存模拟器（已废弃，v2 改用 app.infra.cache.tenant_plan_cache）。
注意：本模块仍注册了旧事件总线主题 'legacy.v1.plan_changed'，但线上无任何读取方消费此缓存。
"""
import threading
import time
from typing import Any, Dict, Optional, Tuple

from app.infra.events import event_bus


class V1MemcachedSlabEmulator:
    def __init__(self, max_keys: int = 2048):
        self._max_keys = max_keys
        self._slabs: Dict[str, Tuple[float, int, Any]] = {}
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._mu = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._mu:
            entry = self._slabs.get(key)
            if entry is None:
                self._misses += 1
                return None
            exp, _, val = entry
            if 0 < exp < time.time():
                del self._slabs[key]
                self._misses += 1
                return None
            self._hits += 1
            return val

    def set(self, key: str, val: Any, exptime: int = 600, flags: int = 0) -> bool:
        with self._mu:
            if len(self._slabs) >= self._max_keys and key not in self._slabs:
                oldest_k = min(self._slabs.keys(), key=lambda k: self._slabs[k][0])
                del self._slabs[oldest_k]
                self._evictions += 1
            exp = (time.time() + exptime) if exptime > 0 else 0.0
            self._slabs[key] = (exp, flags, val)
            return True

    def delete(self, key: str) -> bool:
        with self._mu:
            return self._slabs.pop(key, None) is not None

    def flush_all(self) -> None:
        with self._mu:
            self._slabs.clear()

    def stats(self) -> Dict[str, int]:
        with self._mu:
            return {
                "curr_items": len(self._slabs),
                "get_hits": self._hits,
                "get_misses": self._misses,
                "evictions": self._evictions,
            }


v1_dead_quota_slab = V1MemcachedSlabEmulator()


def _on_v1_plan_event(payload: dict) -> None:
    tid = payload.get("tenant_id")
    if tid:
        v1_dead_quota_slab.delete(f"v1_quota:{tid}")


event_bus.subscribe("legacy.v1.plan_changed", _on_v1_plan_event)
