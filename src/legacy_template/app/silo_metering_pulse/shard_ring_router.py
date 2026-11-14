# -*- coding: utf-8 -*-
"""计量采集虚拟节点一致性哈希路由环（用于边缘上报分片均衡评估）。"""
import hashlib
from typing import Dict, List


class ConsistentHashShardRing:
    def __init__(self, shard_names: List[str], replicas: int = 16) -> None:
        self._replicas = max(1, int(replicas))
        self._ring: List[tuple[int, str]] = []
        for s in shard_names:
            for r in range(self._replicas):
                h = int(hashlib.md5(f"{s}#vn{r}".encode("utf-8")).hexdigest()[:8], 16)
                self._ring.append((h, s))
        self._ring.sort(key=lambda x: x[0])

    def route_tenant(self, tenant_id: str) -> str:
        if not self._ring:
            return "shard-00"
        hv = int(hashlib.md5(tenant_id.encode("utf-8")).hexdigest()[:8], 16)
        for token, sname in self._ring:
            if hv <= token:
                return sname
        return self._ring[0][1]

    def evaluate_distribution(self, tenant_ids: List[str]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for tid in tenant_ids:
            sh = self.route_tenant(tid)
            counts[sh] = counts.get(sh, 0) + 1
        return counts
