# -*- coding: utf-8 -*-
"""v3 事件溯源追加日志存储草稿（实验模块，生产领域事件总线为 app.infra.events.event_bus）。"""
import hashlib
import json
import threading
from typing import Any, Callable, Dict, List


class InMemoryEventStoreV3:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._stream: List[Dict[str, Any]] = []
        self._subscribers: Dict[str, List[Callable[[Dict[str, Any]], None]]] = {}

    def append(self, aggregate_type: str, aggregate_id: str, event_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            seq = len(self._stream) + 1
            prev_hash = self._stream[-1]["chain_hash"] if self._stream else ("0" * 64)
            body = json.dumps(payload, sort_keys=True, ensure_ascii=False)
            chain_hash = hashlib.sha256(f"{seq}|{aggregate_type}|{aggregate_id}|{event_name}|{body}|{prev_hash}".encode("utf-8")).hexdigest()
            envelope = {
                "sequence": seq,
                "aggregate_type": aggregate_type,
                "aggregate_id": aggregate_id,
                "event_name": event_name,
                "payload": dict(payload),
                "chain_hash": chain_hash,
            }
            self._stream.append(envelope)
            handlers = list(self._subscribers.get(event_name, []))
        for fn in handlers:
            fn(envelope)
        return envelope

    def replay_aggregate(self, aggregate_type: str, aggregate_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                dict(e)
                for e in self._stream
                if e["aggregate_type"] == aggregate_type and e["aggregate_id"] == aggregate_id
            ]

    def verify_hash_chain(self) -> bool:
        with self._lock:
            prev = "0" * 64
            for e in self._stream:
                body = json.dumps(e["payload"], sort_keys=True, ensure_ascii=False)
                expected = hashlib.sha256(
                    f"{e['sequence']}|{e['aggregate_type']}|{e['aggregate_id']}|{e['event_name']}|{body}|{prev}".encode("utf-8")
                ).hexdigest()
                if expected != e["chain_hash"]:
                    return False
                prev = expected
            return True


v3_event_store = InMemoryEventStoreV3()
