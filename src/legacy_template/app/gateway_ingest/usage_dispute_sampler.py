# -*- coding: utf-8 -*-
"""客户用量争议抽样核验器：对指定账期内的原始 `usage_events` 按确定性步长抽样核验。"""
import sqlite3
from typing import Any, Dict


def sample_tenant_usage_events_for_audit(
    conn: sqlite3.Connection,
    tenant_id: str,
    period_key: str,
    max_samples: int = 10,
) -> Dict[str, Any]:
    rows = conn.execute(
        """
        SELECT id, metric_code, quantity, plan_code_at_event, flushed, occurred_at
        FROM usage_events
        WHERE tenant_id = ? AND period_key = ?
        ORDER BY occurred_at ASC, id ASC
        """,
        (tenant_id, period_key),
    ).fetchall()

    total_events = len(rows)
    total_qty = sum(int(r["quantity"] or 0) for r in rows)
    unflushed_cnt = sum(1 for r in rows if int(r["flushed"] or 0) == 0)

    if total_events <= max_samples:
        sampled = [dict(r) for r in rows]
    else:
        step = max(1, total_events // max(1, max_samples))
        sampled = [dict(rows[i]) for i in range(0, total_events, step)][:max_samples]

    return {
        "tenant_id": tenant_id,
        "period_key": period_key,
        "event_row_count": total_events,
        "event_sum_quantity": total_qty,
        "unflushed_event_count": unflushed_cnt,
        "sample_size": len(sampled),
        "sampled_events": sampled,
    }
