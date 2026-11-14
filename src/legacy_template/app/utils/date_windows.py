# -*- coding: utf-8 -*-
"""账期时间窗、自然月切分、工作日推算与 ISO8601 兼容解析工具。"""
from datetime import datetime, timedelta, timezone
from typing import List, Tuple


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso_utc(raw: str) -> datetime:
    s = (raw or "").strip()
    if not s:
        return datetime.now(timezone.utc)
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def month_period_bounds(period_key: str) -> Tuple[str, str]:
    parts = period_key.split("-")
    year = int(parts[0])
    month = int(parts[1])
    start = datetime(year, month, 1, 0, 0, 0, tzinfo=timezone.utc)
    if month == 12:
        nxt = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    else:
        nxt = datetime(year, month + 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    return start.strftime("%Y-%m-%dT%H:%M:%SZ"), nxt.strftime("%Y-%m-%dT%H:%M:%SZ")


def previous_period_key(period_key: str, months_back: int = 1) -> str:
    year, month = [int(x) for x in period_key.split("-")]
    total_m = year * 12 + (month - 1) - int(months_back)
    ny = total_m // 12
    nm = (total_m % 12) + 1
    return f"{ny:04d}-{nm:02d}"


def next_period_key(period_key: str, months_ahead: int = 1) -> str:
    return previous_period_key(period_key, -int(months_ahead))


def compute_cycle_remaining_ratio_bps(now_iso: str, cycle_start_iso: str, cycle_end_iso: str) -> int:
    now_dt = parse_iso_utc(now_iso)
    s_dt = parse_iso_utc(cycle_start_iso)
    e_dt = parse_iso_utc(cycle_end_iso)
    total_sec = (e_dt - s_dt).total_seconds()
    if total_sec <= 0:
        return 0
    rem_sec = max(0.0, min(total_sec, (e_dt - now_dt).total_seconds()))
    return int(round((rem_sec / total_sec) * 10000))


def enumerate_period_range(start_period: str, end_period: str) -> List[str]:
    cur = start_period
    out: List[str] = []
    guard = 0
    while cur <= end_period and guard < 120:
        out.append(cur)
        cur = next_period_key(cur, 1)
        guard += 1
    return out


def add_business_days_utc(start_iso: str, business_days: int) -> str:
    dt = parse_iso_utc(start_iso)
    rem = max(0, int(business_days))
    while rem > 0:
        dt += timedelta(days=1)
        if dt.weekday() < 5:
            rem -= 1
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
