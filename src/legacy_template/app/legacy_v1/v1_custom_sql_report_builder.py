# -*- coding: utf-8 -*-
"""2024 V1 遗留：财务月度交叉透视表（套餐档位 × 税制档案）只读聚合统计工具。"""
import sqlite3
from typing import Any, Dict, List

from app.infra.db import parse_legacy_amount_cents


def build_plan_by_tax_profile_pivot(conn: sqlite3.Connection, period_key: str) -> Dict[str, Any]:
    rows = conn.execute(
        """
        SELECT i.*, t.tax_profile_code
        FROM invoices i
        JOIN tenants t ON t.id = i.tenant_id
        WHERE i.period_key = ? AND i.status != 'VOID'
        """,
        (period_key,),
    ).fetchall()

    matrix: Dict[str, Dict[str, int]] = {}
    grand_total = 0

    for r in rows:
        d = dict(r)
        plan = str(d.get("plan_code") or "STARTER")
        tax_p = str(d.get("tax_profile_code") or "CN_VAT_6_INCLUSIVE")
        amt = parse_legacy_amount_cents(d, "total_cents")
        row_bucket = matrix.setdefault(plan, {})
        row_bucket[tax_p] = row_bucket.get(tax_p, 0) + amt
        grand_total += amt

    table_rows: List[Dict[str, Any]] = []
    for plan_code, cols in sorted(matrix.items()):
        table_rows.append({
            "plan_code": plan_code,
            "by_tax_profile_cents": cols,
            "row_total_cents": sum(cols.values()),
        })

    return {
        "period_key": period_key,
        "grand_total_cents": grand_total,
        "pivot_rows": table_rows,
    }
