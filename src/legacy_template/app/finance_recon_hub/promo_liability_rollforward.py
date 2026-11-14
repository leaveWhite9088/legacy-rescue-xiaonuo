# -*- coding: utf-8 -*-
"""营销赠送金池（Promo Credits Roll-Forward）期间发放、核销、退回与到期回收变动底稿。"""
import sqlite3
from typing import Any, Dict


def compute_promo_wallet_rollforward(conn: sqlite3.Connection) -> Dict[str, Any]:
    by_type = conn.execute(
        """
        SELECT entry_type, COALESCE(SUM(promo_delta_cents), 0) AS promo_delta
        FROM wallet_ledger
        GROUP BY entry_type
        """
    ).fetchall()
    buckets = {str(r["entry_type"]): int(r["promo_delta"] or 0) for r in by_type}

    grant_in = buckets.get("PROMO_GRANT", 0)
    consumed_out = buckets.get("INVOICE_PAY", 0) + buckets.get("PAYMENT", 0)
    refund_restored = buckets.get("REFUND", 0)
    expired_out = buckets.get("PROMO_EXPIRE", 0)
    other_net = sum(v for k, v in buckets.items() if k not in ("PROMO_GRANT", "INVOICE_PAY", "PAYMENT", "REFUND", "PROMO_EXPIRE"))

    ledger_ending = grant_in + consumed_out + refund_restored + expired_out + other_net
    w_row = conn.execute("SELECT COALESCE(SUM(promo_balance_cents), 0) AS snap_promo FROM wallets").fetchone()
    snapshot_ending = int(w_row["snap_promo"] or 0) if w_row else 0

    active_grants_row = conn.execute(
        "SELECT COALESCE(SUM(remaining_cents), 0) AS rem FROM promo_grants WHERE status = 'ACTIVE'"
    ).fetchone()
    active_batches_remaining = int(active_grants_row["rem"] or 0) if active_grants_row else 0

    return {
        "cumulative_promo_granted_cents": grant_in,
        "cumulative_promo_consumed_cents": consumed_out,
        "cumulative_promo_refund_restored_cents": refund_restored,
        "cumulative_promo_expired_cents": expired_out,
        "other_promo_delta_cents": other_net,
        "ledger_derived_ending_promo_cents": ledger_ending,
        "wallet_table_snapshot_promo_cents": snapshot_ending,
        "active_grant_batches_sum_cents": active_batches_remaining,
        "ledger_vs_wallet_reconciled": ledger_ending == snapshot_ending,
    }
