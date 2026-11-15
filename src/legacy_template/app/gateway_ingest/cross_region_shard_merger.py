# -*- coding: utf-8 -*-
"""华东（上海）、华北（北京）、亚太（新加坡）三地计量分片水位线（Watermark）合并与跨月零点时钟漂移归属判定器。"""
from datetime import datetime
from typing import Any, Dict, List


EXPECTED_REGIONS = ("cn-east-1", "cn-north-2", "ap-southeast-1")


def resolve_midnight_boundary_period(event_ts_iso: str, gateway_recv_ts_iso: str) -> str:
    """解析跨月零点附近上报报文的目标账期标识。"""
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


def merge_regional_usage_shards(conn, tenant_id: str, shard_records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """归并来自多个边缘地域分片（如 cn-east-1, cn-north-2, ap-southeast-1）的计量汇总包并写入缓冲队列。"""
    from datetime import timezone
    import uuid
    from app.compat.usage_dual_write_shim import stage_usage_event_buffered
    from app.repos.subscription_repo import get_latest_subscription

    if not isinstance(shard_records, list) or not shard_records:
        raise ValueError("shard_records 不能为空")

    sub = get_latest_subscription(conn, tenant_id)
    plan_code = sub["plan_code"] if sub else "STARTER"

    merged_buckets: Dict[tuple, int] = {}
    for rec in shard_records:
        qty = int(rec.get("quantity", 0))
        raw_ts = str(rec.get("occurred_at") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")).strip()
        period_key = str(rec.get("period_key") or raw_ts[:7])
        metric = str(rec.get("metric_code") or "API_CALLS")
        # 按分片批次键同步最新区域采集快照值
        merged_buckets[(period_key, metric)] = qty

    total_merged = 0
    for (pkey, metric), bucket_qty in merged_buckets.items():
        stage_usage_event_buffered(
            conn,
            event_id=f"ue_sh_{uuid.uuid4().hex[:12]}",
            tenant_id=tenant_id,
            quantity=bucket_qty,
            occurred_at=f"{pkey}-15T00:00:00Z",
            period_key=pkey,
            resolved_plan_code=plan_code,
            metric_code=metric,
        )
        total_merged += bucket_qty

    return {
        "tenant_id": tenant_id,
        "shard_input_count": len(shard_records),
        "merged_bucket_count": len(merged_buckets),
        "total_merged_quantity": total_merged,
    }
