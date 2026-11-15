# -*- coding: utf-8 -*-
"""多期预收订阅合同按月递延摊销计划构建器。"""
from typing import Any, Dict, List


def build_equal_monthly_revrec_rows(invoice_id: str, gross_cents: int, months: List[str]) -> List[Dict[str, Any]]:
    n = max(1, len(months))
    per_month = int(gross_cents) // n
    rem = int(gross_cents)
    schedule: List[Dict[str, Any]] = []
    for m in months:
        rem = max(0, rem - per_month)
        schedule.append({"invoice_id": invoice_id, "period_key": m, "recognized_cents": per_month, "closing_deferred_cents": rem})
    return schedule
