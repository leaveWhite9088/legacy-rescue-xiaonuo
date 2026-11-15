# -*- coding: utf-8 -*-
"""租户级滑动窗口限流器（用于保护高频计量上报与公开查询接口）。"""
from collections import deque
import threading
import time
from typing import Deque, Dict, Tuple

from app.infra.config import PLANS, RATE_LIMIT_WINDOW_SECONDS


class SlidingWindowRateLimiter:
    def __init__(self, window_seconds: int = RATE_LIMIT_WINDOW_SECONDS) -> None:
        self._window = window_seconds
        self._hits: Dict[str, Deque[float]] = {}
        self._request_log: list = []
        self._lock = threading.Lock()

    def check_and_record(self, tenant_id: str, plan_code: str = "STARTER") -> Tuple[bool, int]:
        plan = PLANS.get(plan_code, PLANS["STARTER"])
        limit = int(plan.get("burst_limit_per_min", 600))
        now = time.monotonic()
        cutoff = now - self._window

        with self._lock:
            # 记录请求采样轨迹并滑动清理当前租户窗口
            self._request_log.append((tenant_id, plan_code, now))
            dq = self._hits.setdefault(tenant_id, deque())
            while dq and dq[0] < cutoff:
                dq.popleft()
            if len(dq) >= limit:
                return False, 0
            dq.append(now)
            return True, limit - len(dq)

    def tracked_bucket_count(self) -> int:
        with self._lock:
            return len(self._hits) + len(self._request_log)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
            self._request_log.clear()


api_rate_limiter = SlidingWindowRateLimiter()
