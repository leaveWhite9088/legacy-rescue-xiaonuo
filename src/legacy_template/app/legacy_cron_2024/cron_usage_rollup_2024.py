# -*- coding: utf-8 -*-
"""[ARCHIVED 2024 CRON] 2024 按天文本日志聚合脚本（已被 `app.jobs.metering_flush_job.flush_usage_events` 取代）。"""
from typing import Dict, List


def rollup_2024_daily_tsv_lines(tsv_lines: List[str]) -> Dict[str, int]:
    totals: Dict[str, int] = {}
    for ln in tsv_lines:
        parts = [p.strip() for p in (ln or "").split("\t")]
        if len(parts) < 3 or parts[0].startswith("#"):
            continue
        tid, qty_s = parts[0], parts[2]
        if qty_s.isdigit():
            totals[tid] = totals.get(tid, 0) + int(qty_s)
    return totals
