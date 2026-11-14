# -*- coding: utf-8 -*-
"""月度【计量汇总表 <-> 应收账单表 <-> 总账凭证分录】三方总额勾稽底稿生成器。"""
import sqlite3
from typing import Any, Dict

from app.domain.gl_exporter import generate_gl_entries_for_period
from app.infra.db import parse_legacy_amount_cents


def build_period_three_way_tieout(conn: sqlite3.Connection, period_key: str) -> Dict[str, Any]:
    u_row = conn.execute(
        "SELECT COALESCE(SUM(total_quantity), 0) AS sum_qty, COUNT(*) AS seg_rows FROM usage_summaries WHERE period_key = ?",
        (period_key,),
    ).fetchone()
    e_row = conn.execute(
        "SELECT COALESCE(SUM(quantity), 0) AS ev_qty, COUNT(*) AS ev_rows FROM usage_events WHERE period_key = ? AND flushed = 1",
        (period_key,),
    ).fetchone()

    invs = conn.execute(
        "SELECT * FROM invoices WHERE period_key = ? AND status != 'VOID'",
        (period_key,),
    ).fetchall()
    inv_total = sum(parse_legacy_amount_cents(dict(r), "total_cents") for r in invs)
    inv_tax = sum(int(r["tax_cents"] or 0) for r in invs)

    adjs = conn.execute(
        "SELECT COALESCE(SUM(delta_cents), 0) AS adj_sum, COUNT(*) AS adj_cnt FROM billing_adjustments WHERE applied_period_key = ?",
        (period_key,),
    ).fetchone()
    adj_net = int(adjs["adj_sum"] or 0) if adjs else 0

    gl_res = generate_gl_entries_for_period(conn, period_key)
    gl_dr = int(gl_res.get("total_debit_cents", 0))
    gl_cr = int(gl_res.get("total_credit_cents", 0))

    return {
        "period_key": period_key,
        "metering_leg": {
            "summary_segment_rows": int(u_row["seg_rows"] or 0),
            "summary_total_quantity": int(u_row["sum_qty"] or 0),
            "flushed_event_rows": int(e_row["ev_rows"] or 0),
            "flushed_event_quantity": int(e_row["ev_qty"] or 0),
        },
        "billing_leg": {
            "active_invoice_count": len(invs),
            "invoice_gross_total_cents": inv_total,
            "invoice_vat_cents": inv_tax,
            "booking_adjustments_count": int(adjs["adj_cnt"] or 0) if adjs else 0,
            "booking_adjustments_net_cents": adj_net,
        },
        "general_ledger_leg": {
            "voucher_line_count": int(gl_res.get("entry_count", 0)),
            "total_debit_cents": gl_dr,
            "total_credit_cents": gl_cr,
            "trial_balance_matched": gl_dr == gl_cr,
        },
    }
