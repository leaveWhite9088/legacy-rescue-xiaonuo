# -*- coding: utf-8 -*-
"""多租户共享网关突刺流量（Noisy Neighbor）公平队列配额降级判别器。"""
from typing import Any, Dict, List


def detect_noisy_neighbors(samples: List[Dict[str, Any]], cluster_capacity_qps: int = 50000) -> Dict[str, Any]:
    total_qps = sum(max(0, int(s.get("current_qps") or 0)) for s in samples)
    overloaded = total_qps > int(cluster_capacity_qps)
    throttled = []
    for s in samples:
        tid = str(s.get("tenant_id") or "")
        qps = max(0, int(s.get("current_qps") or 0))
        committed_qps = max(10, int(s.get("burst_limit_per_min") or 600) // 60)
        if overloaded and qps > committed_qps * 2:
            throttled.append(
                {
                    "tenant_id": tid,
                    "observed_qps": qps,
                    "committed_qps": committed_qps,
                    "enforced_cap_qps": int(committed_qps * 1.2),
                }
            )
    return {
        "cluster_overloaded": overloaded,
        "total_observed_qps": total_qps,
        "throttled_tenants": throttled,
    }
