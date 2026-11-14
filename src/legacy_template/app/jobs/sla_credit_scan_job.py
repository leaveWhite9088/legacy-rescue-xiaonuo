# -*- coding: utf-8 -*-
"""SLA 月度服务可用性赔付巡检任务。"""
from datetime import datetime, timezone
import sqlite3
from typing import Any, Dict

from app.domain.sla_calculator import compute_sla_breach_credit
from app.infra.config import PLANS


def run_sla_credit_scan_job(conn: sqlite3.Connection, period_key: str) -> Dict[str, Any]:
    rows = conn.execute(
        "SELECT * FROM sla_credit_claims WHERE period_key = ? AND status = 'REPORTED'",
        (period_key,),
    ).fetchall()
    evaluated = 0
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for r in rows:
        sub = conn.execute(
            "SELECT plan_code FROM subscriptions WHERE tenant_id = ? ORDER BY updated_at DESC LIMIT 1",
            (r["tenant_id"],),
        ).fetchone()
        p_code = sub["plan_code"] if sub else "STARTER"
        base_fee = int(PLANS.get(p_code, PLANS["STARTER"])["monthly_fee_cents"])
        res = compute_sla_breach_credit(p_code, base_fee, int(r["observed_uptime_bps"]))
        conn.execute(
            "UPDATE sla_credit_claims SET credit_cents = ?, status = 'EVALUATED', created_at = ? WHERE id = ?",
            (res["credit_cents"], now, r["id"]),
        )
        evaluated += 1
    return {"period_key": period_key, "evaluated_claims": evaluated}
