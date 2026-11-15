# -*- coding: utf-8 -*-
"""总账会计分录（General Ledger）映射生成与试算平衡导出器。"""
from datetime import datetime, timezone
import sqlite3
from typing import Any, Dict, List

from app.infra.db import parse_legacy_amount_cents


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def generate_gl_entries_for_period(conn: sqlite3.Connection, period_key: str) -> Dict[str, Any]:
    """根据账期内有效账单生成总账复式记账凭证摘要（供财务 ERP 对接核对）。"""
    conn.execute("DELETE FROM gl_journal_entries WHERE period_key = ?", (period_key,))
    invoices = conn.execute(
        "SELECT * FROM invoices WHERE period_key = ? AND status != 'VOID'",
        (period_key,),
    ).fetchall()

    now = _now_iso()
    entries: List[Dict[str, Any]] = []
    total_debit = 0
    total_credit = 0

    for inv in invoices:
        d = dict(inv)
        gross = parse_legacy_amount_cents(d, "total_cents")
        if d.get("currency_unit") == "YUAN_STR":
            base_rev = gross
            overage = 0
            late = 0
            tax = 0
        else:
            base_rev = int(d.get("base_fee_cents") or 0)
            overage = int(d.get("overage_fee_cents") or 0)
            late = int(d.get("late_fee_cents") or 0)
            tax = int(d.get("tax_cents") or 0)

        # 借方分录：按账单当前应收总额计入应收账款科目
        if gross > 0:
            conn.execute(
                """
                INSERT INTO gl_journal_entries
                    (period_key, ref_type, ref_id, debit_account, credit_account, amount_cents, debit_cents, credit_cents, created_at)
                VALUES (?, 'INVOICE', ?, '1122-AccountsReceivable', '', ?, ?, 0, ?)
                """,
                (period_key, d["id"], gross, gross, now),
            )
            total_debit += gross
            entries.append({
                "ref_id": d["id"],
                "debit": "1122-AccountsReceivable",
                "credit": "",
                "amount_cents": gross,
                "debit_cents": gross,
                "credit_cents": 0,
            })

        legs = [
            ("6001-SaaSBaseRevenue", base_rev),
            ("6002-UsageOverageRevenue", overage),
            ("6301-LateFeeIncome", late),
            ("2221-TaxPayable", tax),
        ]
        for credit_acct, amt in legs:
            if amt <= 0:
                continue
            conn.execute(
                """
                INSERT INTO gl_journal_entries
                    (period_key, ref_type, ref_id, debit_account, credit_account, amount_cents, debit_cents, credit_cents, created_at)
                VALUES (?, 'INVOICE', ?, '', ?, ?, 0, ?, ?)
                """,
                (period_key, d["id"], credit_acct, amt, amt, now),
            )
            total_credit += amt
            entries.append({
                "ref_id": d["id"],
                "debit": "",
                "credit": credit_acct,
                "amount_cents": amt,
                "debit_cents": 0,
                "credit_cents": amt,
            })

    return {
        "period_key": period_key,
        "entry_count": len(entries),
        "total_debit_cents": total_debit,
        "total_credit_cents": total_credit,
        "balanced": total_debit == total_credit,
    }
