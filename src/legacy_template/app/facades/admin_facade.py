# -*- coding: utf-8 -*-
"""财务与运营管理后台综合门面层。"""
import sqlite3
from typing import Any, Dict

from app.domain.subledger_reconciler import (
    audit_closed_period_seals,
    audit_wallet_vs_ledger_invariants,
)
from app.infra.config import FEATURE_FLAGS
from app.services.admin_service import (
    execute_period_close,
    fetch_accounting_periods,
    fetch_admin_tenants,
    fetch_billing_adjustments,
    fetch_period_reconciliation,
    fetch_recent_audit_logs,
    rebuild_and_fetch_gl_journal,
)
from app.v3_pipeline.shadow_comparator import run_shadow_tariff_diff_sample


def facade_admin_overview(conn: sqlite3.Connection, limit: int = 200) -> Dict[str, Any]:
    return {"tenants": fetch_admin_tenants(conn, limit=limit)}


def facade_admin_periods(conn: sqlite3.Connection) -> Dict[str, Any]:
    return {"periods": fetch_accounting_periods(conn)}


def facade_close_period(conn: sqlite3.Connection, period_key: str, actor: str = "admin_api") -> Dict[str, Any]:
    return execute_period_close(conn, period_key, actor=actor)


def facade_reconcile_period(conn: sqlite3.Connection, period_key: str) -> Dict[str, Any]:
    rep = fetch_period_reconciliation(conn, period_key)
    if FEATURE_FLAGS.get("ENABLE_V3_SHADOW_COMPARATOR", True):
        rep["v3_shadow_sample"] = run_shadow_tariff_diff_sample(conn, period_key, sample_limit=8)
    return rep


def facade_list_adjustments(conn: sqlite3.Connection) -> Dict[str, Any]:
    return {"adjustments": fetch_billing_adjustments(conn)}


def facade_gl_journal(conn: sqlite3.Connection, period_key: str) -> Dict[str, Any]:
    return rebuild_and_fetch_gl_journal(conn, period_key)


def facade_audit_logs(conn: sqlite3.Connection, limit: int = 100) -> Dict[str, Any]:
    return {"logs": fetch_recent_audit_logs(conn, limit=limit)}


def facade_subledger_health(conn: sqlite3.Connection) -> Dict[str, Any]:
    return {
        "wallets_audit": audit_wallet_vs_ledger_invariants(conn),
        "closed_seals": audit_closed_period_seals(conn),
    }
