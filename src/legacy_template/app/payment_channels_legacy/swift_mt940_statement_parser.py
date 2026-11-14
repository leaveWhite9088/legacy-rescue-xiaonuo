# -*- coding: utf-8 -*-
"""跨境外币账户 SWIFT MT940 电文日终水单解析器（供新加坡与香港主体外币收款对账使用）。"""
from typing import Any, Dict, List


def parse_mt940_lines(mt940_text: str) -> Dict[str, Any]:
    account_id = ""
    statement_no = ""
    transactions: List[Dict[str, Any]] = []
    cur_tx: Dict[str, Any] | None = None

    for raw_ln in (mt940_text or "").splitlines():
        ln = raw_ln.strip()
        if ln.startswith(":25:"):
            account_id = ln[4:].strip()
        elif ln.startswith(":28C:"):
            statement_no = ln[5:].strip()
        elif ln.startswith(":61:"):
            body = ln[4:].strip()
            val_date = body[:6]
            dc_mark = "C" if "C" in body[6:9] else "D"
            amt_part = ""
            for ch in body[7:]:
                if ch.isdigit() or ch == ",":
                    amt_part += ch
                elif amt_part:
                    break
            cents = int(round(float(amt_part.replace(",", ".") or "0") * 100))
            cur_tx = {
                "value_date_yymmdd": val_date,
                "direction": "CREDIT" if dc_mark == "C" else "DEBIT",
                "amount_cents": cents,
                "narrative": "",
            }
            transactions.append(cur_tx)
        elif ln.startswith(":86:") and cur_tx is not None:
            cur_tx["narrative"] = ln[4:].strip()

    total_credit = sum(t["amount_cents"] for t in transactions if t["direction"] == "CREDIT")
    total_debit = sum(t["amount_cents"] for t in transactions if t["direction"] == "DEBIT")
    return {
        "account_id": account_id,
        "statement_no": statement_no,
        "tx_count": len(transactions),
        "total_credit_cents": total_credit,
        "total_debit_cents": total_debit,
        "transactions": transactions,
    }
