# -*- coding: utf-8 -*-
"""v3 流式时间窗计量微批聚合器原型（未接入线上路由，生产计量在 app.services.metering_service 与 app.jobs.metering_flush_job）。"""
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple


@dataclass(frozen=True)
class RawMeteringPointV3:
    event_id: str
    tenant_id: str
    metric_code: str
    occurred_at_iso: str
    plan_code_snapshot: str
    delta_units: int


class TumblingWindowAggregatorV3:
    """v3 原型：按 (tenant_id, period_key, plan_code_snapshot) 内存微批去重聚合。
    基于内存时间窗口聚合实时计量事件流。
    """

    def __init__(self) -> None:
        self._seen_ids: set[str] = set()
        self._counters: Dict[Tuple[str, str, str], int] = defaultdict(int)
        self._rejected_non_positive: int = 0

    def ingest_batch(self, points: Iterable[RawMeteringPointV3]) -> Dict[str, int]:
        accepted = 0
        deduped = 0
        for pt in points:
            if pt.event_id in self._seen_ids:
                deduped += 1
                continue
            if int(pt.delta_units) <= 0:
                self._rejected_non_positive += 1
                continue
            self._seen_ids.add(pt.event_id)
            period_key = pt.occurred_at_iso[:7]
            key = (pt.tenant_id, period_key, pt.plan_code_snapshot or "STARTER")
            self._counters[key] += int(pt.delta_units)
            accepted += 1
        return {
            "accepted": accepted,
            "deduped": deduped,
            "rejected_non_positive": self._rejected_non_positive,
        }

    def drain_snapshots(self) -> List[Dict[str, object]]:
        out: List[Dict[str, object]] = []
        for (tid, pk, plan_code), qty in sorted(self._counters.items()):
            out.append({
                "tenant_id": tid,
                "period_key": pk,
                "plan_code": plan_code,
                "aggregated_quantity": qty,
            })
        self._counters.clear()
        return out
