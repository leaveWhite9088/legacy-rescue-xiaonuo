# -*- coding: utf-8 -*-
"""边缘网关脉冲帧（Pulse Frame）滑动窗口压缩与水位线乱序检测器。"""
from datetime import datetime, timezone
from typing import Any, Dict, List


WATERMARK_ALLOWED_LATENESS_SEC = 900  # 15 分钟乱序容忍窗口


def parse_pulse_iso_epoch(ts_text: str) -> int:
    s = (ts_text or "").strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def compact_gateway_pulse_frames(frames: List[Dict[str, Any]], watermark_epoch: int) -> Dict[str, Any]:
    in_window: Dict[str, int] = {}
    late_frames: List[Dict[str, Any]] = []
    seen_frame_ids: set[str] = set()
    dup_dropped = 0

    for fr in frames:
        fid = str(fr.get("frame_id") or "")
        if fid:
            if fid in seen_frame_ids:
                dup_dropped += 1
                continue
            seen_frame_ids.add(fid)

        ep = parse_pulse_iso_epoch(str(fr.get("ts") or "2026-11-01T00:00:00Z"))
        pulses = max(0, int(fr.get("pulse_qty") or 0))
        tenant_key = str(fr.get("tenant_id") or "unknown")
        utc_month = datetime.fromtimestamp(ep, tz=timezone.utc).strftime("%Y-%m")

        if watermark_epoch - ep > WATERMARK_ALLOWED_LATENESS_SEC:
            late_frames.append({"tenant_id": tenant_key, "utc_month": utc_month, "pulses": pulses, "epoch": ep})
        else:
            bucket = f"{tenant_key}::{utc_month}"
            in_window[bucket] = in_window.get(bucket, 0) + pulses

    return {
        "compacted_buckets": in_window,
        "late_frame_count": len(late_frames),
        "late_frames": late_frames,
        "duplicate_dropped": dup_dropped,
    }
