# -*- coding: utf-8 -*-
"""飞书与钉钉财务值班群机器人卡片组装器（沙盒离线队列缓冲模式，不发起真实公网请求）。"""
import threading
from typing import Any, Dict, List

_outbox_lock = threading.Lock()
_im_card_buffer: List[Dict[str, Any]] = []


def enqueue_ops_im_card(channel: str, severity: str, title: str, fields: Dict[str, Any]) -> Dict[str, Any]:
    card = {
        "channel": channel,
        "severity": severity,
        "msg_type": "interactive",
        "header": {"title": f"[{severity}] {title}", "template": "red" if severity == "CRITICAL" else "orange"},
        "elements": [{"key": str(k), "value": str(v)} for k, v in fields.items()],
    }
    with _outbox_lock:
        if len(_im_card_buffer) >= 200:
            del _im_card_buffer[:100]
        _im_card_buffer.append(card)
    return card


def drain_ops_im_cards() -> List[Dict[str, Any]]:
    with _outbox_lock:
        items = list(_im_card_buffer)
        _im_card_buffer.clear()
        return items
