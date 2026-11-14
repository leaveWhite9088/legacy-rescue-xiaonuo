# -*- coding: utf-8 -*-
"""逾期账单催收升级批处理任务。"""
import sqlite3
from typing import Any, Dict

from app.domain.dunning_engine import evaluate_overdue_portfolio


def run_dunning_escalation_job(conn: sqlite3.Connection, as_of_iso: str) -> Dict[str, Any]:
    rep = evaluate_overdue_portfolio(conn, as_of_iso=as_of_iso, persist_cases=True)
    return {
        "evaluated_overdue_cases": rep["overdue_count"],
        "total_overdue_cents": rep["total_overdue_cents"],
        "stage_distribution": rep["stage_distribution"],
    }
