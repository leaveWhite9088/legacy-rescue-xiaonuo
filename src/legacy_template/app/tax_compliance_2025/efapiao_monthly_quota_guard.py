# -*- coding: utf-8 -*-
"""金税四期乐企月度授信开票额度（授信池余量预警与提额申请判断）。"""
import sqlite3
from typing import Any, Dict


def check_monthly_efapiao_credit_pool(
    conn: sqlite3.Connection,
    period_key: str,
    bureau_granted_pool_cents: int = 500_000_000,
) -> Dict[str, Any]:
    prefix = period_key.replace("-", "")
    row = conn.execute(
        """
        SELECT COALESCE(SUM(CASE WHEN gross_amount_cents > 0 THEN gross_amount_cents ELSE 0 END), 0) AS blue_used,
               COALESCE(SUM(CASE WHEN gross_amount_cents < 0 THEN ABS(gross_amount_cents) ELSE 0 END), 0) AS red_restored
        FROM fapiao_requests
        WHERE id LIKE ?
        """,
        (f"%{prefix}%",),
    ).fetchone()
    net_consumed = max(0, int(row["blue_used"] or 0) - int(row["red_restored"] or 0))
    rem = max(0, int(bureau_granted_pool_cents) - net_consumed)
    used_bps = (net_consumed * 10000) // max(1, int(bureau_granted_pool_cents))
    return {
        "period_key": period_key,
        "granted_pool_cents": int(bureau_granted_pool_cents),
        "net_consumed_cents": net_consumed,
        "remaining_pool_cents": rem,
        "utilization_bps": used_bps,
        "require_bureau_limit_increase": used_bps >= 8500,
    }
