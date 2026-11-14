# -*- coding: utf-8 -*-
"""[V3 EXPERIMENTAL DRAFT] 基于一致性哈希环的事务发件箱（Transactional Outbox）分区路由器草稿。"""
import hashlib
from typing import Any, Dict, List


class V3ConsistentHashOutboxRouter:
    def __init__(self, partition_count: int = 8, virtual_nodes: int = 16) -> None:
        self.partition_count = max(1, int(partition_count))
        self.virtual_nodes = max(1, int(virtual_nodes))
        self._ring: List[tuple] = []
        for p in range(self.partition_count):
            for vn in range(self.virtual_nodes):
                h = int(hashlib.md5(f"part-{p}-vn-{vn}".encode("utf-8")).hexdigest()[:8], 16)
                self._ring.append((h, p))
        self._ring.sort(key=lambda x: x[0])

    def route_tenant_partition(self, tenant_id: str) -> int:
        key_h = int(hashlib.md5((tenant_id or "default").encode("utf-8")).hexdigest()[:8], 16)
        for ring_h, p_idx in self._ring:
            if key_h <= ring_h:
                return p_idx
        return self._ring[0][1]

    def plan_outbox_batch_partitions(self, events: List[Dict[str, Any]]) -> Dict[int, List[str]]:
        grouped: Dict[int, List[str]] = {i: [] for i in range(self.partition_count)}
        for ev in events:
            tid = str(ev.get("tenant_id") or "default")
            p_idx = self.route_tenant_partition(tid)
            grouped[p_idx].append(str(ev.get("id") or ""))
        return grouped
