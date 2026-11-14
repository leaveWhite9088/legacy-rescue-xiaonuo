# -*- coding: utf-8 -*-
"""高调用量低单价大客户（Whale Tenants）算力毛利倒挂预警分析器。
业务背景：部分 2024 `ACTIVE_LEGACY` 老客户签署了 `LEGACY_FLAT_99` 或封顶条款，虽然受终身保价协议保护不可单方面涨价或清退，
但财务与架构团队需持续监控其算力成本占比，引导客户自愿采购增值插件。
"""
import sqlite3
from typing import Any, Dict, List

from app.finops_cost_allocation.cloud_cogs_allocator import compute_period_tenant_gross_margins


def detect_margin_inverted_whales(conn: sqlite3.Connection, period_key: str = "2026-11") -> Dict[str, Any]:
    margin_report = compute_period_tenant_gross_margins(conn, period_key)
    watch_list: List[Dict[str, Any]] = []

    for row in margin_report["tenants"]:
        if row["usage_quantity"] >= 30_000 and row["gross_margin_bps"] < 3500:
            t_info = conn.execute("SELECT status, tier_level FROM tenants WHERE id = ?", (row["tenant_id"],)).fetchone()
            st = str(t_info["status"]) if t_info else "ACTIVE"
            watch_list.append({
                **row,
                "tenant_status": st,
                "contractually_grandfathered": st == "ACTIVE_LEGACY",
                "recommended_action": (
                    "KEEP_GRANDFATHERED_OFFER_OPTIONAL_ADDON"
                    if st == "ACTIVE_LEGACY"
                    else "REVIEW_DISCOUNT_AT_NEXT_RENEWAL"
                ),
            })

    return {
        "period_key": period_key,
        "whale_warning_count": len(watch_list),
        "watch_list": watch_list,
    }
