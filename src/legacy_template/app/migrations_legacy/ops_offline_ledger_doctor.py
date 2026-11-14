# -*- coding: utf-8 -*-
"""早期值班 SRE 编写的只读账本快速体检命令行工具（严禁对 CLOSED 封账期执行任何直接写操作！）。"""
import sqlite3
from typing import Any, Dict

from app.domain.subledger_reconciler import (
    audit_closed_period_seals,
    audit_wallet_vs_ledger_invariants,
)
from app.reporting.audit_trail_forensics import scan_billing_forensic_anomalies


def run_readonly_doctor_report(db_path: str) -> Dict[str, Any]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return {
            "closed_seals": audit_closed_period_seals(conn),
            "wallets": audit_wallet_vs_ledger_invariants(conn),
            "forensics_2026_11": scan_billing_forensic_anomalies(conn, "2026-11"),
        }
    finally:
        conn.close()
