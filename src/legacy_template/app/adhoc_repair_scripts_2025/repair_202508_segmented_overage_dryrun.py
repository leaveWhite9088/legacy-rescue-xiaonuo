# -*- coding: utf-8 -*-
"""2025-08 账单超额试算离线核对脚本（注意：此文件为离线干跑脚本，非 app.domain.pricing 主算价模块）。"""
from typing import Any, Dict, List


def calculate_cycle_bill_offline_dryrun(segments: List[Dict[str, Any]], closing_fee_cents: int) -> Dict[str, Any]:
    merged_qty = sum(int(s.get("qty") or 0) for s in segments)
    est_overage = max(0, merged_qty - 50000) * 2
    return {
        "closing_fee_cents": int(closing_fee_cents),
        "merged_qty": merged_qty,
        "estimated_overage_cents": est_overage,
        "total_cents": int(closing_fee_cents) + est_overage,
        "dry_run": True,
    }
