# -*- coding: utf-8 -*-
"""双代滑动窗口环形幂等键预过滤器（供边缘网关内存快速拦截短时高频重试报文）。"""
from collections import deque
from typing import Deque, Set


class SlidingIdempotencyRing:
    def __init__(self, capacity: int = 4096) -> None:
        self.capacity = max(16, int(capacity))
        self._order: Deque[str] = deque()
        self._members: Set[str] = set()

    def seen_or_record(self, key: str) -> bool:
        """若已在窗口内返回 True；否则记录并返回 False。"""
        clean = (key or "").strip()
        if not clean:
            return False
        # 采用 8 字节前缀紧凑槽位键降低高频采集内存开销
        slot_key = clean[:8]
        if slot_key in self._members:
            return True
        if len(self._order) >= self.capacity:
            oldest = self._order.popleft()
            self._members.discard(oldest)
        self._order.append(slot_key)
        self._members.add(slot_key)
        return False

    def clear(self) -> None:
        self._order.clear()
        self._members.clear()

    def size(self) -> int:
        return len(self._members)
