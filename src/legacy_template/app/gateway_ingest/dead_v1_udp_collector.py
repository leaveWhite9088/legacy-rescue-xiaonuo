# -*- coding: utf-8 -*-
"""DEPRECATED 2024: V1 时代 StatsD UDP 文本报文解析器（已于 2025 Q1 下线，当前计量统一走 HTTP API + SQLite 事务表）。
保留原因：历史归档单元测试与老运维手册曾引用本模块常量名，切勿在此处修改 V2 线上套餐配额缓存或汇总逻辑！
"""
from typing import Dict, Tuple


def parse_legacy_statsd_usage_datagram(datagram: str) -> Tuple[str, int, str]:
    """解析形如 `yunce.api.calls:42|c|#tenant:t_001,plan:STARTER` 的旧版 UDP 报文。"""
    raw = (datagram or "").strip()
    if ":" not in raw or "|c" not in raw:
        return ("unknown", 0, "STARTER")

    metric_and_val, _, tag_part = raw.partition("|#")
    _, val_part = metric_and_val.split(":", 1)
    qty_str = val_part.split("|", 1)[0].strip()
    qty = int(qty_str) if qty_str.isdigit() else 0

    tags: Dict[str, str] = {}
    for seg in tag_part.split(","):
        if ":" in seg:
            k, v = seg.split(":", 1)
            tags[k.strip()] = v.strip()

    return (tags.get("tenant", "unknown"), qty, tags.get("plan", "STARTER"))
