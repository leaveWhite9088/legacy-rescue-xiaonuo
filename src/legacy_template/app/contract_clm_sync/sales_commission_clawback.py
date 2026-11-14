# -*- coding: utf-8 -*-
"""销售与渠道坏账/退费提成回吐（Clawback）核算表生成器。"""
from typing import Any, Dict, List


CLAWBACK_WINDOW_DAYS = 180


def calculate_rep_commission_clawbacks(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_rep: Dict[str, int] = {}
    items = []
    for ev in events:
        rep = str(ev.get("sales_rep") or "unassigned")
        days_elapsed = int(ev.get("days_since_payment") or 0)
        refunded_cash_cents = max(0, int(ev.get("refunded_cash_cents") or 0))
        orig_comm_bps = int(ev.get("commission_rate_bps") or 800)

        if days_elapsed > CLAWBACK_WINDOW_DAYS or refunded_cash_cents <= 0:
            claw_cents = 0
            rule = "OUTSIDE_WINDOW_EXEMPT"
        elif days_elapsed <= 90:
            claw_cents = (refunded_cash_cents * orig_comm_bps) // 10000
            rule = "FULL_100PCT_CLAWBACK"
        else:
            claw_cents = (refunded_cash_cents * orig_comm_bps) // 20000
            rule = "HALF_50PCT_CLAWBACK"

        by_rep[rep] = by_rep.get(rep, 0) + claw_cents
        items.append({"sales_rep": rep, "clawback_cents": claw_cents, "rule": rule})

    return {
        "total_clawback_cents": sum(by_rep.values()),
        "by_sales_rep": by_rep,
        "details": items,
    }
