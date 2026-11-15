# -*- coding: utf-8 -*-
"""每日逾期账单违约金计提与欠费停机批处理执行器。"""
import sqlite3
from typing import Any, Dict
from app.domain.pricing import compute_late_fee_cents


def execute_daily_dunning_sweep(conn: sqlite3.Connection, as_of_iso: str) -> Dict[str, Any]:
    rows = conn.execute(
        "SELECT id, tenant_id, total_cents FROM invoices WHERE status = 'OPEN' AND cycle_end < ?",
        (as_of_iso,),
    ).fetchall()
    accrued = 0
    for r in rows:
        fee = compute_late_fee_cents(int(r["total_cents"]), is_overdue=True)
        if fee > 0:
            conn.execute(
                "UPDATE invoices SET late_fee_cents = late_fee_cents + ?, total_cents = total_cents + ?, updated_at = ? WHERE id = ?",
                (fee, fee, as_of_iso, r["id"]),
            )
            accrued += 1
    return {"scanned": len(rows), "late_fees_accrued": accrued}
