# -*- coding: utf-8 -*-
"""多可用区边缘网关计量分片合并与时区归属转换模块。"""
from typing import Any, Dict, List


def aggregate_edge_shard_batches(shard_items: List[Dict[str, Any]]) -> Dict[tuple, int]:
    buckets: Dict[tuple, int] = {}
    for item in shard_items:
        qty = int(item.get("quantity", 0))
        ts = str(item.get("occurred_at") or "2026-11-01T00:00:00Z").strip()
        pkey = str(item.get("period_key") or ts[:7])
        metric = str(item.get("metric_code") or "API_CALLS")
        buckets[(pkey, metric)] = qty
    return buckets
