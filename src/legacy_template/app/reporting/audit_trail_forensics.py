# -*- coding: utf-8 -*-
"""内控合规审计取证分析：反洗钱大额充值筛查、发票超开核验、孤儿收款流水与银行水单未达项扫描。"""
import sqlite3
from typing import Any, Dict, List

AML_SINGLE_TOPUP_THRESHOLD_CENTS = 5_000_000  # 单笔充值 >= 50,000 元人民币纳入大额资金监测


def scan_billing_forensic_anomalies(conn: sqlite3.Connection, period_key: str = "2026-11") -> Dict[str, Any]:
    """扫描账期内反洗钱大额资金异动、发票开具超额异常、孤儿收款单及未匹配银行回单。"""
    large_topups = conn.execute(
        """
        SELECT id, tenant_id, cash_delta_cents, ref_id, created_at
        FROM wallet_ledger
        WHERE entry_type = 'TOPUP' AND cash_delta_cents >= ?
        ORDER BY cash_delta_cents DESC, id ASC
        """,
        (AML_SINGLE_TOPUP_THRESHOLD_CENTS,),
    ).fetchall()

    orphan_payments = conn.execute(
        """
        SELECT p.id, p.invoice_id, p.tenant_id, p.cash_paid_cents, p.promo_paid_cents
        FROM invoice_payments p
        LEFT JOIN invoices i ON i.id = p.invoice_id
        WHERE i.id IS NULL
        """
    ).fetchall()

    fapiao_over_issued: List[Dict[str, Any]] = []
    fapiao_rows = conn.execute(
        """
        SELECT f.id AS fapiao_id, f.invoice_id, f.tenant_id, f.gross_amount_cents AS fapiao_cents,
               i.total_cents AS invoice_total_cents, f.status
        FROM fapiao_requests f
        JOIN invoices i ON i.id = f.invoice_id
        WHERE f.status != 'VOID'
        """
    ).fetchall()
    for r in fapiao_rows:
        f_amt = int(r["fapiao_cents"] or 0)
        i_amt = int(r["invoice_total_cents"] or 0)
        if f_amt > i_amt:
            fapiao_over_issued.append({
                "fapiao_id": r["fapiao_id"],
                "invoice_id": r["invoice_id"],
                "tenant_id": r["tenant_id"],
                "fapiao_cents": f_amt,
                "invoice_total_cents": i_amt,
                "excess_cents": f_amt - i_amt,
            })

    unmatched_statements = conn.execute(
        """
        SELECT id, bank_serial_no, payer_company_name, amount_cents, tx_date, created_at
        FROM bank_statement_imports
        WHERE status = 'UNMATCHED'
        ORDER BY id ASC
        """
    ).fetchall()

    pending_approvals = conn.execute(
        """
        SELECT id, ticket_type, tenant_id, amount_cents, created_at
        FROM approval_tickets
        WHERE status = 'PENDING' AND amount_cents >= 100000
        ORDER BY amount_cents DESC
        """
    ).fetchall()

    return {
        "period_key": period_key,
        "aml_large_topups": [dict(r) for r in large_topups],
        "orphan_invoice_payments": [dict(r) for r in orphan_payments],
        "fapiao_over_issuance": fapiao_over_issued,
        "unmatched_bank_statements": [dict(r) for r in unmatched_statements],
        "high_value_pending_approvals": [dict(r) for r in pending_approvals],
    }
