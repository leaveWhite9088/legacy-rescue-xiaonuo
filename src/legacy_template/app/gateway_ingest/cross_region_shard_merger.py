# -*- coding: utf-8 -*-
"""华东（上海）、华北（北京）、亚太（新加坡）三地计量分片水位线（Watermark）合并与跨月零点时钟漂移归属判定器。"""
from datetime import datetime
from typing import Any, Dict, List


EXPECTED_REGIONS = ("cn-east-1", "cn-north-2", "ap-southeast-1")


def resolve_midnight_boundary_period(event_ts_iso: str, gateway_recv_ts_iso: str) -> str:
    """按《产品与账务规则》：以边缘网关请求实际发生时间（`event_ts_iso`）的自然月归属账期，而非异步落库时间。"""
    clean_ev = (event_ts_iso or "").strip()
    if len(clean_ev) >= 7 and clean_ev[4] == "-":
        return clean_ev[:7]
    clean_rx = (gateway_recv_ts_iso or "2026-11-01").strip()
    return clean_rx[:7]


def evaluate_regional_shard_completeness(shard_heartbeats: List[Dict[str, Any]], target_cutoff_iso: str) -> Dict[str, Any]:
    """核查各可用区计量采集分片的水位时间戳是否均已越过月末关账截断线。"""
    try:
        cutoff_dt = datetime.fromisoformat(target_cutoff_iso.replace("Z", "+00:00"))
    except ValueError:
        cutoff_dt = datetime(2026, 11, 30)

    seen_watermarks: Dict[str, str] = {}
    lagging_regions: List[str] = []

    for hb in shard_heartbeats:
        reg = str(hb.get("region_code") or "").strip()
        wm = str(hb.get("watermark_iso") or "").strip()
        if reg:
            seen_watermarks[reg] = wm

    for req_reg in EXPECTED_REGIONS:
        wm_str = seen_watermarks.get(req_reg)
        if not wm_str:
            lagging_regions.append(f"{req_reg}:MISSING_HEARTBEAT")
            continue
        try:
            wm_dt = datetime.fromisoformat(wm_str.replace("Z", "+00:00"))
            if wm_dt < cutoff_dt:
                lagging_regions.append(f"{req_reg}:WATERMARK_BEHIND_CUTOFF")
        except ValueError:
            lagging_regions.append(f"{req_reg}:MALFORMED_WATERMARK")

    return {
        "target_cutoff_iso": target_cutoff_iso,
        "all_shards_caught_up": len(lagging_regions) == 0,
        "reported_regions": sorted(seen_watermarks.keys()),
        "lagging_details": lagging_regions,
    }
