# -*- coding: utf-8 -*-
"""2024 第一代 API 网关话单 (CDR - Call Detail Record) 离线文本清洗与去重归并器 (LEGACY)。
背景：2024 年边缘网关每小时落地文本话单日志，经本模块去重、纠偏时区偏移、映射历史指标名后导入数据库。
2025 年实时 HTTP /api/usage/events 上线后，本模块仅用于边缘断网重传离线包的恢复清洗。
"""
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any, Deque, Dict, Iterable, List, Set, Tuple

LEGACY_METRIC_ALIASES_2024: Dict[str, Tuple[str, int]] = {
    "API_CALLS": ("API_CALLS", 1),
    "GW_HTTP_REQ": ("API_CALLS", 1),
    "BATCH_OCR_PAGE": ("API_CALLS", 5),
    "DOC_PARSE_HEAVY": ("API_CALLS", 10),
    "WEBHOOK_PUSH_ATTEMPT": ("API_CALLS", 1),
    "HEARTBEAT_PING": ("IGNORED", 0),
}


class BoundedRequestDeduplicator:
    """固定容量环形滑动集合，过滤网关重试产生的重复话单 ID。"""

    def __init__(self, capacity: int = 8192):
        self.capacity = max(64, int(capacity))
        self._ring: Deque[str] = deque()
        self._seen: Set[str] = set()

    def check_and_mark(self, cdr_id: str) -> bool:
        if not cdr_id:
            return False
        if cdr_id in self._seen:
            return False
        if len(self._ring) >= self.capacity:
            evicted = self._ring.popleft()
            self._seen.discard(evicted)
        self._ring.append(cdr_id)
        self._seen.add(cdr_id)
        return True


def normalize_cdr_timestamp_to_utc(raw_ts: str, source_tz_offset_hours: int = 8) -> Tuple[str, str]:
    """将早期无时区后缀的网关本地时间（默认东八区）统一折算为 UTC ISO8601 与对应自然月账期。"""
    s = (raw_ts or "").strip()
    if not s:
        now = datetime.now(timezone.utc)
        return now.strftime("%Y-%m-%dT%H:%M:%SZ"), now.strftime("%Y-%m")

    if s.endswith("Z") or "+" in s[10:]:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    else:
        naive = datetime.fromisoformat(s.replace(" ", "T"))
        src_tz = timezone(timedelta(hours=int(source_tz_offset_hours)))
        dt = naive.replace(tzinfo=src_tz).astimezone(timezone.utc)

    return dt.strftime("%Y-%m-%dT%H:%M:%SZ"), dt.strftime("%Y-%m")


def process_legacy_cdr_lines(
    raw_lines: Iterable[str],
    max_single_event_qty: int = 500_000,
) -> Dict[str, Any]:
    """解析竖线分隔话单行：cdr_id|tenant_id|metric_alias|raw_count|local_timestamp"""
    deduper = BoundedRequestDeduplicator(capacity=16384)
    aggregated: Dict[Tuple[str, str, str], int] = {}
    quarantine: List[Dict[str, Any]] = []
    duplicate_count = 0
    ignored_heartbeat_count = 0
    accepted_count = 0

    for line_no, raw in enumerate(raw_lines, start=1):
        txt = (raw or "").strip()
        if not txt or txt.startswith("#"):
            continue
        parts = [p.strip() for p in txt.split("|")]
        if len(parts) != 5:
            quarantine.append({"line_no": line_no, "reason": "MALFORMED_COLUMN_COUNT", "raw": txt[:120]})
            continue

        cdr_id, tenant_id, alias, cnt_str, ts_str = parts
        if not tenant_id.startswith("t_"):
            quarantine.append({"line_no": line_no, "reason": "INVALID_TENANT_PREFIX", "tenant_id": tenant_id})
            continue

        if not deduper.check_and_mark(cdr_id):
            duplicate_count += 1
            continue

        mapped_metric, weight = LEGACY_METRIC_ALIASES_2024.get(alias.upper(), ("UNKNOWN", 0))
        if mapped_metric == "IGNORED":
            ignored_heartbeat_count += 1
            continue
        if mapped_metric == "UNKNOWN":
            quarantine.append({"line_no": line_no, "reason": "UNKNOWN_METRIC_ALIAS", "alias": alias})
            continue

        try:
            raw_qty = int(cnt_str)
        except ValueError:
            quarantine.append({"line_no": line_no, "reason": "NON_INTEGER_QUANTITY", "value": cnt_str})
            continue

        if raw_qty <= 0 or raw_qty > max_single_event_qty:
            quarantine.append({"line_no": line_no, "reason": "OUT_OF_RANGE_QUANTITY", "quantity": raw_qty})
            continue

        try:
            _, period_key = normalize_cdr_timestamp_to_utc(ts_str)
        except Exception:
            quarantine.append({"line_no": line_no, "reason": "INVALID_TIMESTAMP", "timestamp": ts_str})
            continue

        weighted_qty = raw_qty * weight
        key = (tenant_id, period_key, mapped_metric)
        aggregated[key] = aggregated.get(key, 0) + weighted_qty
        accepted_count += 1

    rollups = [
        {
            "tenant_id": tid,
            "period_key": pk,
            "metric_code": m_code,
            "normalized_quantity": qty,
        }
        for (tid, pk, m_code), qty in sorted(aggregated.items())
    ]

    return {
        "accepted_records": accepted_count,
        "duplicate_records": duplicate_count,
        "ignored_heartbeats": ignored_heartbeat_count,
        "quarantined_records": len(quarantine),
        "quarantine_samples": quarantine[:50],
        "rollups": rollups,
    }
