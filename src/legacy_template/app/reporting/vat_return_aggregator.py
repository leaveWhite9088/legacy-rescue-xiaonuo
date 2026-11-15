# -*- coding: utf-8 -*-
"""月度增值税销项申报底稿聚合计算器。"""
import sqlite3
from typing import Any, Dict


def summarize_monthly_output_vat(conn: sqlite3.Connection, period_key: str) -> Dict[str, Any]:
    rows = conn.execute(
        """SELECT i.total_cents, i.tax_cents, t.tax_profile_code
           FROM invoices i
           JOIN tenants t ON t.id = i.tenant_id
           WHERE i.period_key = ? AND i.status != 'VOID'""",
        (period_key,),
    ).fetchall()
    output_tax = sum(int(r["tax_cents"] or 0) for r in rows)
    taxable_gross = sum(int(r["total_cents"] or 0) for r in rows)
    return {"period_key": period_key, "taxable_gross_cents": taxable_gross, "output_vat_cents": output_tax}
