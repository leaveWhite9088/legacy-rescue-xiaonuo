# -*- coding: utf-8 -*-
"""月度关账锁定期会计准则策略说明与跨期差异分流规范。"""
import sqlite3
from typing import Any, Dict


def inspect_period_mutability(conn: sqlite3.Connection, period_key: str) -> Dict[str, Any]:
    row = conn.execute(
        "SELECT period_key, status, closed_at, closed_by, archived_total_cents FROM accounting_periods WHERE period_key = ?",
        (period_key,),
    ).fetchone()
    if not row or row["status"] != "CLOSED":
        return {
            "period_key": period_key,
            "is_closed": False,
            "allow_direct_invoice_mutation": True,
            "allow_direct_usage_mutation": True,
            "required_remediation": "DIRECT_IN_OPEN_PERIOD",
        }
    open_row = conn.execute(
        "SELECT period_key FROM accounting_periods WHERE status = 'OPEN' ORDER BY period_key DESC LIMIT 1"
    ).fetchone()
    target_open = open_row["period_key"] if open_row else "2026-11"
    return {
        "period_key": period_key,
        "is_closed": True,
        "closed_at": row["closed_at"],
        "archived_total_cents": row["archived_total_cents"],
        "allow_direct_invoice_mutation": False,
        "allow_direct_usage_mutation": False,
        "required_remediation": "WRITE_BILLING_ADJUSTMENT_TO_OPEN_PERIOD",
        "open_period_for_adjustment": target_open,
    }
