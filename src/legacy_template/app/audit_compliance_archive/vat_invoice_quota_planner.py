# -*- coding: utf-8 -*-
"""月度税务局数电发票授信总额度（授信制开票限额）消耗预警与增版增量测算器。"""
import sqlite3
from typing import Any, Dict


def evaluate_monthly_tax_bureau_quota_usage(
    conn: sqlite3.Connection,
    monthly_bureau_quota_cents: int = 200_000_000,
) -> Dict[str, Any]:
    row = conn.execute(
        "SELECT COALESCE(SUM(gross_amount_cents), 0) AS issued_gross, COUNT(*) AS cnt FROM fapiao_requests WHERE status = 'ISSUED'"
    ).fetchone()
    used_cents = max(0, int(row["issued_gross"] or 0)) if row else 0
    quota = max(1, int(monthly_bureau_quota_cents))
    usage_bps = int((used_cents * 10000) // quota)

    return {
        "monthly_bureau_quota_cents": quota,
        "issued_blue_gross_cents": used_cents,
        "remaining_quota_cents": max(0, quota - used_cents),
        "utilization_bps": usage_bps,
        "needs_quota_expansion_filing": usage_bps >= 8000,
    }
