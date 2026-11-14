# -*- coding: utf-8 -*-
"""[V3 EXPERIMENTAL DRAFT] 第三代分布式租约锁与单调递增围栏令牌（Fencing Token）内存原型。
工程警告：本模块仅在单进程字典中模拟租约协调，并未接入 SQLite 跨连接事务锁！
V2 生产环境的真实并发扣款保护必须依托数据库层事务（如 `BEGIN IMMEDIATE`）与条件状态原子更新实现。
"""
from dataclasses import dataclass
import time
from typing import Dict, Optional


@dataclass
class V3LeaseEntry:
    resource_key: str
    holder_id: str
    fencing_token: int
    expires_at_monotonic: float


class V3InMemoryLeaseCoordinator:
    def __init__(self) -> None:
        self._sequence: int = 1000
        self._leases: Dict[str, V3LeaseEntry] = {}

    def try_acquire(self, resource_key: str, holder_id: str, ttl_seconds: float = 5.0) -> Optional[V3LeaseEntry]:
        now = time.monotonic()
        existing = self._leases.get(resource_key)
        if existing is not None and existing.expires_at_monotonic > now and existing.holder_id != holder_id:
            return None
        self._sequence += 1
        lease = V3LeaseEntry(
            resource_key=resource_key,
            holder_id=holder_id,
            fencing_token=self._sequence,
            expires_at_monotonic=now + max(0.1, float(ttl_seconds)),
        )
        self._leases[resource_key] = lease
        return lease

    def release(self, resource_key: str, holder_id: str, fencing_token: int) -> bool:
        existing = self._leases.get(resource_key)
        if existing is None:
            return False
        if existing.holder_id != holder_id or existing.fencing_token != fencing_token:
            return False
        del self._leases[resource_key]
        return True

    def inspect_active_count(self) -> int:
        now = time.monotonic()
        return sum(1 for v in self._leases.values() if v.expires_at_monotonic > now)
