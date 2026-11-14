# -*- coding: utf-8 -*-
"""进程内领域事件总线：用于解耦订阅变更、缓存失效、审计日志与渠道通知。"""
from collections import defaultdict
import threading
from typing import Any, Callable, Dict, List

from app.infra.logger import get_logger

log = get_logger("yunce.events")

EventHandler = Callable[[Dict[str, Any]], None]


class DomainEventBus:
    def __init__(self) -> None:
        self._subscribers: Dict[str, List[EventHandler]] = defaultdict(list)
        self._lock = threading.RLock()

    def subscribe(self, topic: str, handler: EventHandler) -> None:
        with self._lock:
            if handler not in self._subscribers[topic]:
                self._subscribers[topic].append(handler)

    def publish(self, topic: str, payload: Dict[str, Any]) -> int:
        with self._lock:
            handlers = list(self._subscribers.get(topic, []))
        invoked = 0
        for h in handlers:
            try:
                h(payload)
                invoked += 1
            except Exception as exc:
                log.warning("event handler error on topic=%s: %s", topic, exc)
        return invoked


event_bus = DomainEventBus()
