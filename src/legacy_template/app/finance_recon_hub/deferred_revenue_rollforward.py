# -*- coding: utf-8 -*-
"""预收账款-客户现金池（Deferred Cash Roll-Forward）期间变动调节底稿生成器（四大事务所外审标准附表）。"""
import sqlite3
from typing import Any, Dict


def compute_cash_wallet_rollforward(conn: sqlite3.Connection) -> Dict[str, Any]:
    """按全量资金流水分类汇总：`充值流入 - 账单消费扣减 + 账单现金退回 = 当前应有现金池总余额`。"""
    by_type = conn.execute(
        """
        SELECT entry_type, COALESCE(SUM(cash_delta_cents), 0) AS cash_delta
        FROM wallet_ledger
        GROUP BY entry_type
        """
    ).fetchall()
    buckets = {str(r["entry_type"]): int(r["cash_delta"] or 0) for r in by_type}

    topup_in = buckets.get("TOPUP", 0)
    payment_out = buckets.get("INVOICE_PAY", 0) + buckets.get("PAYMENT", 0)    # 负数
    refund_in = buckets.get("REFUND", 0)                                       # 正数
    other_net = sum(v for k, v in buckets.items() if k not in ("TOPUP", "INVOICE_PAY", "PAYMENT", "REFUND"))

    ledger_derived_ending = topup_in + payment_out + refund_in + other_net
    w_row = conn.execute("SELECT COALESCE(SUM(cash_balance_cents), 0) AS snap_cash FROM wallets").fetchone()
    snapshot_ending = int(w_row["snap_cash"] or 0) if w_row else 0

    return {
        "cumulative_topup_inflow_cents": topup_in,
        "cumulative_invoice_payment_outflow_cents": payment_out,
        "cumulative_cash_refund_restored_cents": refund_in,
        "other_adjustments_cents": other_net,
        "ledger_derived_ending_cash_cents": ledger_derived_ending,
        "wallet_table_snapshot_cash_cents": snapshot_ending,
        "reconciled": ledger_derived_ending == snapshot_ending,
        "variance_cents": snapshot_ending - ledger_derived_ending,
    }
