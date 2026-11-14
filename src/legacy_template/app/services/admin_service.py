# -*- coding: utf-8 -*-
"""财务与运营管理后台编排服务：租户总览、关账、渠道返佣、总账凭证与审计日志。"""
import sqlite3
from typing import Any, Dict, List

from app.domain.gl_exporter import generate_gl_entries_for_period
from app.domain.partner_commission import calculate_period_partner_commissions
from app.domain.reconcile import build_reconciliation_report, close_accounting_period
from app.repos.tenant_repo import list_all_tenants_overview


def fetch_admin_tenants(conn: sqlite3.Connection, limit: int = 200) -> List[Dict[str, Any]]:
    return list_all_tenants_overview(conn, limit=limit)


def fetch_accounting_periods(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    rows = conn.execute("SELECT * FROM accounting_periods ORDER BY period_key DESC").fetchall()
    return [dict(r) for r in rows]


def execute_period_close(conn: sqlite3.Connection, period_key: str, actor: str = "admin_api") -> Dict[str, Any]:
    return close_accounting_period(conn, period_key, actor=actor)


def fetch_period_reconciliation(conn: sqlite3.Connection, period_key: str) -> Dict[str, Any]:
    return build_reconciliation_report(conn, period_key)


def fetch_billing_adjustments(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    rows = conn.execute("SELECT * FROM billing_adjustments ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def run_and_fetch_partner_commissions(conn: sqlite3.Connection, period_key: str) -> List[Dict[str, Any]]:
    return calculate_period_partner_commissions(conn, period_key)


def rebuild_and_fetch_gl_journal(conn: sqlite3.Connection, period_key: str) -> Dict[str, Any]:
    summary = generate_gl_entries_for_period(conn, period_key)
    rows = conn.execute(
        "SELECT * FROM gl_journal_entries WHERE period_key = ? ORDER BY id ASC LIMIT 200",
        (period_key,),
    ).fetchall()
    return {**summary, "entries": [dict(r) for r in rows]}


def fetch_recent_audit_logs(conn: sqlite3.Connection, limit: int = 100) -> List[Dict[str, Any]]:
    rows = conn.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]
