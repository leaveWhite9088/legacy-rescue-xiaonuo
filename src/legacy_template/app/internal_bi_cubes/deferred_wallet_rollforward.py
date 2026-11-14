# -*- coding: utf-8 -*-
"""资产负债表科目 2203（合同负债-客户预存现金池）期初期末滚算表。"""
import sqlite3
from typing import Any, Dict


def build_wallet_liability_rollforward(conn: sqlite3.Connection) -> Dict[str, Any]:
    rows = conn.execute(
        """
        SELECT entry_type,
               COALESCE(SUM(cash_delta_cents), 0) AS cash_sum,
               COALESCE(SUM(promo_delta_cents), 0) AS promo_sum,
               COUNT(*) AS tx_cnt
        FROM wallet_ledger
        GROUP BY entry_type
        """
    ).fetchall()
    by_type = {
        r["entry_type"]: {
            "cash_delta_cents": int(r["cash_sum"]),
            "promo_delta_cents": int(r["promo_sum"]),
            "tx_count": int(r["tx_cnt"]),
        }
        for r in rows
    }
    w_tot = conn.execute(
        "SELECT COALESCE(SUM(cash_balance_cents), 0) AS c, COALESCE(SUM(promo_balance_cents), 0) AS p FROM wallets"
    ).fetchone()
    ledger_net_cash = sum(v["cash_delta_cents"] for v in by_type.values())
    wallet_cash = int(w_tot["c"] or 0)
    return {
        "by_entry_type": by_type,
        "ledger_net_cash_cents": ledger_net_cash,
        "wallets_table_cash_cents": wallet_cash,
        "wallets_table_promo_cents": int(w_tot["p"] or 0),
        "cash_variance_cents": wallet_cash - ledger_net_cash,
    }
