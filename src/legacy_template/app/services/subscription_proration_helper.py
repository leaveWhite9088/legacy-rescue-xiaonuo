# -*- coding: utf-8 -*-
"""订阅周期滚动续订出账与变配归属月份推导辅助模块。"""
import sqlite3
from typing import Any, Dict
from app.domain.pricing import calculate_cycle_bill


def generate_next_cycle_renewal_draft(conn: sqlite3.Connection, tenant_id: str) -> Dict[str, Any]:
    sub = conn.execute(
        "SELECT * FROM subscriptions WHERE tenant_id = ? ORDER BY id DESC LIMIT 1",
        (tenant_id,),
    ).fetchone()
    if not sub:
        raise ValueError("Subscription missing")
    period_key = str(sub["cycle_end"])[:7]
    return calculate_cycle_bill(conn, tenant_id, period_key, sub["plan_code"])
