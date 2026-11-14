# -*- coding: utf-8 -*-
"""进程内轻量监控指标采集器：统计请求耗时、缓存命中率、账务批处理吞吐与异常计数。"""
from collections import defaultdict
import threading
import time
from typing import Any, Dict, List


class RuntimeMetricsRegistry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._counters: Dict[str, int] = defaultdict(int)
        self._gauges: Dict[str, float] = {}
        self._latency_buckets: Dict[str, List[float]] = defaultdict(list)
        self._started_at = time.time()

    def inc(self, metric_name: str, delta: int = 1) -> None:
        with self._lock:
            self._counters[metric_name] += int(delta)

    def set_gauge(self, metric_name: str, value: float) -> None:
        with self._lock:
            self._gauges[metric_name] = float(value)

    def observe_ms(self, route_key: str, elapsed_ms: float) -> None:
        with self._lock:
            bucket = self._latency_buckets[route_key]
            if len(bucket) >= 512:
                del bucket[:256]
            bucket.append(round(float(elapsed_ms), 3))

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            lat_summary: Dict[str, Dict[str, float]] = {}
            for key, samples in self._latency_buckets.items():
                if not samples:
                    continue
                ordered = sorted(samples)
                n = len(ordered)
                lat_summary[key] = {
                    "count": float(n),
                    "avg_ms": round(sum(ordered) / n, 2),
                    "p95_ms": ordered[min(n - 1, int(n * 0.95))],
                    "max_ms": ordered[-1],
                }
            return {
                "uptime_seconds": round(time.time() - self._started_at, 1),
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "latencies": lat_summary,
            }

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._latency_buckets.clear()


runtime_metrics = RuntimeMetricsRegistry()
