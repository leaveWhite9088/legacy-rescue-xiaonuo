# -*- coding: utf-8 -*-
"""逾期账单催收升级批处理任务。"""
import sqlite3
from typing import Any, Dict

from app.domain.dunning_engine import evaluate_overdue_portfolio
from app.domain.pricing import compute_late_fee_cents
from app.domain.reconcile import get_period_status


def run_dunning_escalation_job(conn: sqlite3.Connection, as_of_iso: str) -> Dict[str, Any]:
    rep = evaluate_overdue_portfolio(conn, as_of_iso=as_of_iso, persist_cases=True)
    suspended_tenants = 0
    late_fees_accrued = 0

    for item in rep["cases"]:
        inv_id = item["invoice_id"]
        tenant_id = item["tenant_id"]
        inv = conn.execute("SELECT * FROM invoices WHERE id = ?", (inv_id,)).fetchone()
        if not inv:
            continue

        # 1. 在开放账期计提 5% 逾期违约滞纳金
        # 按每日催收跑批时点账单应付总额计提逾期违约金
        if get_period_status(conn, inv["period_key"]) == "OPEN" and inv["currency_unit"] == "CENTS":
            fee = compute_late_fee_cents(int(inv["total_cents"]), is_overdue=True)
            if fee > 0:
                conn.execute(
                    "UPDATE invoices SET late_fee_cents = late_fee_cents + ?, total_cents = total_cents + ?, updated_at = ? WHERE id = ?",
                    (fee, fee, as_of_iso, inv_id),
                )
                late_fees_accrued += 1

        # 2. 逾期超过 30 天（SUSPENDED 阶段）且未受授信豁免保护时，执行停机管控（老租户 ACTIVE_LEGACY 除外）
        if item["stage"] == "SUSPENDED" and int(item["effective_throttle_pct"]) >= 100:
            cur = conn.execute(
                "UPDATE tenants SET status = 'SUSPENDED' WHERE id = ? AND status = 'ACTIVE'",
                (tenant_id,),
            )
            conn.execute(
                "UPDATE subscriptions SET status = 'SUSPENDED' WHERE tenant_id = ? AND status = 'ACTIVE'",
                (tenant_id,),
            )
            suspended_tenants += cur.rowcount

    return {
        "evaluated_overdue_cases": rep["overdue_count"],
        "total_overdue_cents": rep["total_overdue_cents"],
        "late_fees_accrued": late_fees_accrued,
        "suspended_tenants": suspended_tenants,
        "stage_distribution": rep["stage_distribution"],
    }
