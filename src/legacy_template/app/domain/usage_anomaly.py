# -*- coding: utf-8 -*-
"""租户 API 用量突增与死循环盗刷异常检测算法。"""
import sqlite3
from typing import Any, Dict, List

from app.utils.calc_helpers import compute_z_score


def detect_period_usage_spikes(conn: sqlite3.Connection, target_period: str = "2026-11", z_threshold: float = 2.5) -> List[Dict[str, Any]]:
    tenants = conn.execute("SELECT id, company_name FROM tenants WHERE status IN ('ACTIVE', 'ACTIVE_LEGACY')").fetchall()
    alerts: List[Dict[str, Any]] = []

    for t in tenants:
        tid = t["id"]
        hist_rows = conn.execute(
            """
            SELECT period_key, SUM(total_quantity) AS qty
            FROM usage_summaries
            WHERE tenant_id = ?
            GROUP BY period_key
            ORDER BY period_key ASC
            """,
            (tid,),
        ).fetchall()
        if len(hist_rows) < 3:
            continue
        by_pk = {r["period_key"]: float(r["qty"] or 0) for r in hist_rows}
        if target_period not in by_pk:
            continue
        prior_vals = [v for k, v in by_pk.items() if k < target_period]
        if len(prior_vals) < 2:
            continue
        cur_val = by_pk[target_period]
        z = compute_z_score(cur_val, prior_vals)
        if z >= z_threshold and cur_val > 20_000:
            alerts.append({
                "tenant_id": tid,
                "company_name": t["company_name"],
                "period_key": target_period,
                "current_quantity": int(cur_val),
                "historical_mean": round(sum(prior_vals) / len(prior_vals), 1),
                "z_score": round(z, 2),
            })
    return alerts
