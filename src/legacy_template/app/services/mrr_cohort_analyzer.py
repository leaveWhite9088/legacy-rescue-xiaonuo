# -*- coding: utf-8 -*-
"""订阅队列经常性收入（MRR）与净回款效率分析组件。"""
import sqlite3
from typing import Any, Dict
from app.infra.config import PLANS


def summarize_subscription_mrr_snapshot(conn: sqlite3.Connection, period_key: str = "2026-11") -> Dict[str, Any]:
    rows = conn.execute("SELECT plan_code, status, COUNT(*) AS cnt FROM subscriptions GROUP BY plan_code, status").fetchall()
    mrr = 0
    for r in rows:
        if r["status"] != "EXPIRED":
            mrr += int(PLANS.get(r["plan_code"], PLANS["STARTER"])["monthly_fee_cents"]) * int(r["cnt"])
    invs = conn.execute("SELECT total_cents, paid_cents FROM invoices WHERE period_key = ? AND status != 'VOID'", (period_key,)).fetchall()
    billed = sum(int(x["total_cents"] or 0) for x in invs)
    collected = sum(int(x["paid_cents"] or 0) for x in invs)
    return {"period_key": period_key, "active_mrr_cents": mrr, "billed_cents": billed, "collected_cents": collected}
