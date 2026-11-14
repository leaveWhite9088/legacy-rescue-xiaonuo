# -*- coding: utf-8 -*-
"""2025 H1 小时级 API 网关用量分桶聚合辅助类（仅供离线趋势图抽样，不参与正式账单结算）。"""
from typing import Any, Dict, List


def bucket_events_by_hour(events: List[Dict[str, Any]]) -> Dict[str, int]:
    buckets: Dict[str, int] = {}
    for ev in events:
        ts = str(ev.get("recorded_at") or "")
        hour_key = ts[:13] if len(ts) >= 13 else "UNKNOWN_HOUR"
        buckets[hour_key] = buckets.get(hour_key, 0) + max(0, int(ev.get("quantity") or 0))
    return dict(sorted(buckets.items()))
