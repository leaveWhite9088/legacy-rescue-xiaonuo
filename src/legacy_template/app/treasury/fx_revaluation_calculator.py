# -*- coding: utf-8 -*-
"""外币账单锁汇折算与期末汇兑重估计算引擎。"""
import sqlite3
from typing import Any, Dict


def compute_period_fx_revaluation_delta(
    conn: sqlite3.Connection,
    period_key: str,
    closing_rates_bps: Dict[str, int],
) -> Dict[str, Any]:
    rows = conn.execute(
        """SELECT f.invoice_id, f.currency_code, f.foreign_minor_units, f.applied_rate_bps, f.settled_cny_cents, i.status
           FROM fx_settlement_logs f
           JOIN invoices i ON i.id = f.invoice_id
           WHERE i.period_key = ?""",
        (period_key,),
    ).fetchall()
    total_delta = 0
    for r in rows:
        rate = int(closing_rates_bps.get(r["currency_code"], r["applied_rate_bps"]))
        closing_cny = (int(r["foreign_minor_units"]) * rate + 5000) // 10000
        total_delta += int(r["settled_cny_cents"]) - closing_cny
    return {"period_key": period_key, "count": len(rows), "net_fx_gain_loss_cents": total_delta}
