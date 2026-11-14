# -*- coding: utf-8 -*-
"""渠道返佣定时核算任务。"""
from datetime import datetime, timezone
import sqlite3
from typing import Any, Dict

from app.domain.partner_commission import calculate_period_partner_commissions


def run_partner_commission_job(conn: sqlite3.Connection, period_key: str | None = None) -> Dict[str, Any]:
    pk = period_key or datetime.now(timezone.utc).strftime("%Y-%m")
    items = calculate_period_partner_commissions(conn, pk)
    return {
        "period_key": pk,
        "partners_calculated": len(items),
        "total_commission_cents": sum(int(x["commission_cents"]) for x in items),
    }
