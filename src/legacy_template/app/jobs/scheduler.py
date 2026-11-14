# -*- coding: utf-8 -*-
"""后台定时任务统一调度器：编排计量刷盘、赠金到期、周期续费、自动扣款、死信重试与催收升级。"""
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.domain.ledger import expire_promo_grants
from app.infra.db import tx_context
from app.jobs.commission_job import run_partner_commission_job
from app.jobs.dlq_retry_job import retry_pending_dlq
from app.jobs.dunning_escalation_job import run_dunning_escalation_job
from app.jobs.metering_flush_job import flush_usage_events
from app.jobs.metrics_rollup_job import run_metrics_rollup_job
from app.jobs.settlement_job import generate_due_cycle_invoices, settle_open_invoices


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_all_jobs(db_path: Optional[str] = None, as_of_iso: Optional[str] = None) -> Dict[str, Any]:
    now = as_of_iso or _now_iso()
    period_key = now[:7]
    with tx_context(db_path, immediate=True) as conn:
        flush_res = flush_usage_events(conn)
        expire_res = expire_promo_grants(conn, as_of_iso=now)
        gen_res = generate_due_cycle_invoices(conn, as_of_iso=now)
        settle_res = settle_open_invoices(conn)
        dlq_res = retry_pending_dlq(conn)
        comm_res = run_partner_commission_job(conn, period_key=period_key)
        dunning_res = run_dunning_escalation_job(conn, as_of_iso=now)
        rollup_res = run_metrics_rollup_job(conn)
    return {
        "as_of": now,
        "metering_flush": flush_res,
        "promo_expiry": expire_res,
        "cycle_billing": gen_res,
        "auto_settlement": settle_res,
        "dlq_retry": dlq_res,
        "partner_commission": comm_res,
        "dunning_escalation": dunning_res,
        "metrics_rollup": rollup_res,
    }
