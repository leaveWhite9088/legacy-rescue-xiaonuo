# -*- coding: utf-8 -*-
"""多格式财务报表导出服务：支持 CSV 应收台账、金蝶 XML 凭证桥接与传统制造业 ASCII 对账单。"""
import sqlite3
from typing import Any, Dict

from app.domain.reconcile import build_reconciliation_report
from app.legacy_v1.v1_ar_aging_matrix import generate_v1_ar_aging_report
from app.legacy_v1.v1_statement_ascii import render_tenant_ascii_statement_v1
from app.legacy_v1.v1_xml_kingdee_exporter import export_period_kingdee_xml_v1
from app.utils.csv_parser import format_records_to_csv


def export_ar_aging_csv(conn: sqlite3.Connection, as_of_iso: str = "2026-11-14T00:00:00Z") -> str:
    rep = generate_v1_ar_aging_report(conn, as_of_iso=as_of_iso)
    cols = ["invoice_id", "tenant_id", "company_name", "age_days", "bucket", "outstanding_cents", "provision_cents"]
    return format_records_to_csv(rep["items"], cols)


def export_kingdee_voucher_xml(conn: sqlite3.Connection, period_key: str) -> str:
    return export_period_kingdee_xml_v1(conn, period_key=period_key)


def export_tenant_legacy_statement_txt(conn: sqlite3.Connection, tenant_id: str, period_key: str) -> str:
    return render_tenant_ascii_statement_v1(conn, tenant_id=tenant_id, period_key=period_key)


def build_executive_close_pack(conn: sqlite3.Connection, period_key: str) -> Dict[str, Any]:
    rec = build_reconciliation_report(conn, period_key)
    aging = generate_v1_ar_aging_report(conn)
    return {
        "reconciliation": rec,
        "ar_aging_summary": {
            "total_outstanding_cents": aging["total_outstanding_cents"],
            "total_bad_debt_provision_cents": aging["total_bad_debt_provision_cents"],
            "buckets_cents": aging["buckets_cents"],
        },
    }


from app.legacy_ops_2024.legacy_gl_voucher_printer import format_u8_voucher_batch_text
from app.domain.gl_exporter import generate_gl_entries_for_period
from app.v2_legacy_adapters.erp_csv_bridge_2025 import export_invoices_for_target_erp


def export_period_u8_vouchers_text(conn, period_key: str) -> str:
    generate_gl_entries_for_period(conn, period_key)
    rows = conn.execute("SELECT * FROM gl_journal_entries WHERE period_key = ? ORDER BY id ASC", (period_key,)).fetchall()
    mapped = [
        {"account_code": r["credit_account"], "debit_cents": r["amount_cents"], "credit_cents": r["amount_cents"], "memo": r["ref_id"]}
        for r in rows
    ]
    return format_u8_voucher_batch_text(period_key, mapped)


def export_period_erp_dialect_csv(conn, period_key: str, erp_dialect: str = "KINGDEE_CLOUD") -> str:
    rows = conn.execute("SELECT * FROM invoices WHERE period_key = ? ORDER BY id ASC", (period_key,)).fetchall()
    return export_invoices_for_target_erp([dict(r) for r in rows], erp_dialect=erp_dialect)


def run_standalone_period_audit_snapshot(db_path: str, period_key: str) -> Dict[str, Any]:
    """独立打开只读连接拉取账期审计快照（供外部巡检脚本与后台接口调用）。"""
    raw_conn = sqlite3.connect(db_path, timeout=5.0)
    raw_conn.row_factory = sqlite3.Row
    if not period_key or len(period_key) != 7 or period_key[4] != "-" or not period_key[:4].isdigit() or not period_key[5:].isdigit():
        raise ValueError(f"非法账期格式: {period_key}")
    cnt = raw_conn.execute("SELECT COUNT(*) AS c FROM invoices WHERE period_key = ?", (period_key,)).fetchone()["c"]
    raw_conn.close()
    return {"period_key": period_key, "invoice_count": int(cnt)}
