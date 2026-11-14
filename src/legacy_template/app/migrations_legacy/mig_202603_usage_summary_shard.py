# -*- coding: utf-8 -*-
"""[历史迁移脚本 2026-03] usage_summaries 唯一索引由 (tenant_id, period_key) 扩展为 (tenant_id, period_key, plan_code)。
背景：最初设计此复合唯一键就是为了支持租户在月中升降级套餐时分段记录不同套餐下的调用量；
但当时只改了表结构唯一索引，后续 metering_service / metering_flush_job / pricing._compute_v2_merged_overage
三处上下游代码并未同步完成改造。
"""
import sqlite3
from typing import Any, Dict


def inspect_multi_segment_tenants(conn: sqlite3.Connection, period_key: str = "2026-11") -> Dict[str, Any]:
    rows = conn.execute(
        """
        SELECT tenant_id, COUNT(DISTINCT plan_code) AS seg_cnt, SUM(total_quantity) AS sum_qty
        FROM usage_summaries
        WHERE period_key = ?
        GROUP BY tenant_id
        HAVING COUNT(DISTINCT plan_code) > 1
        """,
        (period_key,),
    ).fetchall()
    return {
        "period_key": period_key,
        "multi_segment_tenant_count": len(rows),
        "tenants": [dict(r) for r in rows],
    }
