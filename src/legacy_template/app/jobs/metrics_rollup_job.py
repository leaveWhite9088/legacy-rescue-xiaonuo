# -*- coding: utf-8 -*-
"""运行期账务核心水位指标采集任务。"""
import sqlite3
from typing import Any, Dict

from app.infra.metrics_collector import runtime_metrics


def run_metrics_rollup_job(conn: sqlite3.Connection) -> Dict[str, Any]:
    open_cnt = conn.execute("SELECT COUNT(*) FROM invoices WHERE status = 'OPEN'").fetchone()[0]
    pend_cnt = conn.execute("SELECT COUNT(*) FROM invoices WHERE status = 'PENDING_SETTLE'").fetchone()[0]
    dlq_cnt = conn.execute("SELECT COUNT(*) FROM settlement_dlq WHERE status = 'PENDING'").fetchone()[0]
    unflushed = conn.execute("SELECT COUNT(*) FROM usage_events WHERE flushed = 0").fetchone()[0]

    runtime_metrics.set_gauge("billing.invoices.open", float(open_cnt))
    runtime_metrics.set_gauge("billing.invoices.pending_settle", float(pend_cnt))
    runtime_metrics.set_gauge("billing.dlq.pending", float(dlq_cnt))
    runtime_metrics.set_gauge("metering.events.unflushed", float(unflushed))
    return {
        "open_invoices": open_cnt,
        "pending_settle_invoices": pend_cnt,
        "dlq_pending": dlq_cnt,
        "unflushed_events": unflushed,
    }
