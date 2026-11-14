# -*- coding: utf-8 -*-
"""应收账款周转天数（DSO）与回款账龄健康度指标计算器。"""
import sqlite3
from typing import Any, Dict

from app.infra.db import parse_legacy_amount_cents


def compute_dso_metrics(conn: sqlite3.Connection, ref_period: str = "2026-10", period_days: int = 30) -> Dict[str, Any]:
    credit_sales_rows = conn.execute(
        "SELECT * FROM invoices WHERE period_key = ? AND status != 'VOID'",
        (ref_period,),
    ).fetchall()
    period_sales_cents = sum(parse_legacy_amount_cents(dict(r)) for r in credit_sales_rows)

    open_ar_rows = conn.execute(
        "SELECT * FROM invoices WHERE status IN ('OPEN', 'PENDING_SETTLE', 'PARTIAL_PAID', 'DISPUTED')"
    ).fetchall()
    ending_ar_cents = sum(max(0, parse_legacy_amount_cents(dict(r)) - int(r["paid_cents"])) for r in open_ar_rows)

    if period_sales_cents <= 0:
        dso_days = 0.0
    else:
        dso_days = round((ending_ar_cents / float(period_sales_cents)) * period_days, 2)

    return {
        "reference_period": ref_period,
        "period_credit_sales_cents": period_sales_cents,
        "ending_open_ar_cents": ending_ar_cents,
        "dso_days": dso_days,
        "health_rating": "HEALTHY" if dso_days <= 35.0 else ("WATCH" if dso_days <= 60.0 else "CRITICAL"),
    }
