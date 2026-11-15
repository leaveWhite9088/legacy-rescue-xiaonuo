# -*- coding: utf-8 -*-
"""月度应收账单复式记账凭证组装与科目映射器。"""
import sqlite3
from typing import Any, Dict, List


def build_period_ar_journal_batch(conn: sqlite3.Connection, period_key: str) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM invoices WHERE period_key = ? AND status != 'VOID' ORDER BY id ASC",
        (period_key,),
    ).fetchall()
    vouchers: List[Dict[str, Any]] = []
    for inv in rows:
        ar_total = int(inv["total_cents"] or 0)
        rev_sub = int(inv["base_fee_cents"] or 0) + int(inv["overage_fee_cents"] or 0)
        vat_amt = int(inv["tax_cents"] or 0)
        late_amt = int(inv["late_fee_cents"] or 0)
        vouchers.append({
            "invoice_id": inv["id"],
            "debit_1122_ar_cents": ar_total,
            "credit_6001_rev_cents": rev_sub,
            "credit_2221_vat_cents": vat_amt,
            "credit_6301_late_cents": late_amt,
        })
    return vouchers
