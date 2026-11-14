# -*- coding: utf-8 -*-
"""自动扣款结算死信队列（`settlement_dlq`）故障归因分类与重放计划评估器。"""
import sqlite3
from typing import Any, Dict, List

DLQ_CATEGORY_RULES = (
    ("GATEWAY_TIMEOUT", ("timeout", "timed out", "504", "gateway")),
    ("ACCOUNT_FROZEN_OR_LIMIT", ("frozen", "risk", "limit", "suspended")),
    ("INSUFFICIENT_FUNDS", ("insufficient", "balance", "shortfall", "余额不足")),
    ("CONCURRENCY_LOCK", ("locked", "busy", "conflict")),
)


def classify_dlq_error_message(err_msg: str) -> str:
    low = (err_msg or "").lower()
    for cat, keywords in DLQ_CATEGORY_RULES:
        if any(k in low for k in keywords):
            return cat
    return "UNCLASSIFIED_SETTLEMENT_ERROR"


def inspect_settlement_dlq_backlog(conn: sqlite3.Connection) -> Dict[str, Any]:
    rows = conn.execute(
        """
        SELECT d.*, i.period_key, i.status AS current_invoice_status, i.total_cents
        FROM settlement_dlq d
        LEFT JOIN invoices i ON i.id = d.invoice_id
        ORDER BY d.id ASC
        """
    ).fetchall()

    by_category: Dict[str, int] = {}
    items: List[Dict[str, Any]] = []
    retryable_count = 0

    for r in rows:
        cat = classify_dlq_error_message(str(r["error_msg"] or ""))
        by_category[cat] = by_category.get(cat, 0) + 1
        inv_st = str(r["current_invoice_status"] or "UNKNOWN")
        can_retry = inv_st == "OPEN" and int(r["retry_count"] or 0) < 5
        if can_retry:
            retryable_count += 1
        items.append({
            "dlq_id": r["id"],
            "invoice_id": r["invoice_id"],
            "tenant_id": r["tenant_id"],
            "period_key": r["period_key"],
            "invoice_status": inv_st,
            "total_cents": int(r["total_cents"] or 0),
            "error_category": cat,
            "retry_count": int(r["retry_count"] or 0),
            "safe_to_retry_now": can_retry,
        })

    return {
        "total_dlq_entries": len(items),
        "retryable_open_entries": retryable_count,
        "by_category": by_category,
        "entries": items,
    }
