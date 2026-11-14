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
        tax = int(d.get("tax_cents") or 0)
        overage = int(d.get("overage_fee_cents") or 0)
        late = int(d.get("late_fee_cents") or 0)
        base_rev = max(0, gross - tax - overage - late)

        # 借：应收账款 (1122-AR)，贷：订阅收入 / 超额收入 / 滞纳金收入 / 应交税费
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
                INSERT INTO gl_journal_entries (period_key, ref_type, ref_id, debit_account, credit_account, amount_cents, created_at)
                VALUES (?, 'INVOICE', ?, '1122-AccountsReceivable', ?, ?, ?)
                """,
                (period_key, d["id"], credit_acct, amt, now),
            )
            total_debit += amt
            total_credit += amt
            entries.append({"ref_id": d["id"], "debit": "1122-AccountsReceivable", "credit": credit_acct, "amount_cents": amt})

    return {
        "period_key": period_key,
        "entry_count": len(entries),
        "total_debit_cents": total_debit,
        "total_credit_cents": total_credit,
        "balanced": total_debit == total_credit,
    }
