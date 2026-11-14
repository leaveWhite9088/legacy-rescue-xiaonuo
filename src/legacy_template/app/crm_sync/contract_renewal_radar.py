# -*- coding: utf-8 -*-
"""企业客户合同到期续约雷达（90/60/30 天预警窗、自动续约退订截止日与 CPI 价格指数联动测算）。"""
from datetime import datetime, timedelta
import sqlite3
from typing import Any, Dict, List


def _parse_ymd(date_str: str) -> datetime:
    clean = (date_str or "2026-12-31")[:10]
    try:
        return datetime.strptime(clean, "%Y-%m-%d")
    except ValueError:
        return datetime(2026, 12, 31)


def scan_upcoming_contract_renewals(
    conn: sqlite3.Connection,
    as_of_ymd: str = "2026-11-14",
    horizon_days: int = 120,
    cpi_index_bps: int = 220,
) -> Dict[str, Any]:
    now_dt = _parse_ymd(as_of_ymd)
    contracts = conn.execute(
        """
        SELECT c.*, t.company_name, t.status AS tenant_status, s.plan_code
        FROM enterprise_contracts c
        JOIN tenants t ON t.id = c.tenant_id
        LEFT JOIN subscriptions s ON s.tenant_id = c.tenant_id
        ORDER BY c.valid_until ASC
        """
    ).fetchall()

    radar_items: List[Dict[str, Any]] = []
    at_risk_arr_cents = 0

    for row in contracts:
        end_dt = _parse_ymd(str(row["valid_until"] or "2026-12-31"))
        days_left = (end_dt - now_dt).days
        if days_left < -30 or days_left > horizon_days:
            continue

        opt_out_deadline_dt = end_dt - timedelta(days=30)
        auto_renew_locked = now_dt > opt_out_deadline_dt

        min_commit = int(row["min_monthly_commit_cents"] or 0)
        current_arr = min_commit * 12
        uplift_bps = min(800, max(500, int(cpi_index_bps) + 200))
        target_renewal_monthly = min_commit + (min_commit * uplift_bps) // 10000

        risk_invs = conn.execute(
            "SELECT COUNT(*) AS cnt FROM invoices WHERE tenant_id = ? AND status IN ('DISPUTED', 'PAST_DUE')",
            (row["tenant_id"],),
        ).fetchone()
        has_billing_friction = int(risk_invs["cnt"] or 0) > 0 if risk_invs else False
        if has_billing_friction:
            at_risk_arr_cents += current_arr

        urgency = "CRITICAL_30D" if days_left <= 30 else ("HIGH_60D" if days_left <= 60 else "NORMAL_120D")
        radar_items.append({
            "contract_id": row["id"],
            "tenant_id": row["tenant_id"],
            "company_name": row["company_name"],
            "plan_code": row["plan_code"],
            "valid_until": str(row["valid_until"])[:10],
            "days_until_expiry": days_left,
            "urgency_bucket": urgency,
            "opt_out_deadline": opt_out_deadline_dt.strftime("%Y-%m-%d"),
            "auto_renew_window_locked": auto_renew_locked,
            "current_min_commit_cents": min_commit,
            "proposed_renewal_commit_cents": target_renewal_monthly,
            "has_open_billing_friction": has_billing_friction,
        })

    return {
        "as_of": as_of_ymd,
        "horizon_days": horizon_days,
        "upcoming_count": len(radar_items),
        "friction_at_risk_arr_cents": at_risk_arr_cents,
        "contracts": radar_items,
    }
