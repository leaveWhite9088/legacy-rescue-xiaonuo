# -*- coding: utf-8 -*-
"""四维子账本勾稽关系校验引擎（供财务内审、健康诊断接口及关账前置检查使用）。"""
import sqlite3
from typing import Any, Dict, List

from app.infra.db import parse_legacy_amount_cents


def audit_wallet_vs_ledger_invariants(conn: sqlite3.Connection) -> Dict[str, Any]:
    """核查所有租户钱包快照是否出现负余额，以及与流水表净额的偏差。"""
    wallets = conn.execute("SELECT * FROM wallets ORDER BY tenant_id ASC").fetchall()
    negative_wallets: List[Dict[str, Any]] = []
    ledger_drifts: List[Dict[str, Any]] = []

    for w in wallets:
        tid = w["tenant_id"]
        c_bal = int(w["cash_balance_cents"])
        p_bal = int(w["promo_balance_cents"])
        if c_bal < 0 or p_bal < 0:
            negative_wallets.append({
                "tenant_id": tid,
                "cash_balance_cents": c_bal,
                "promo_balance_cents": p_bal,
            })

        sums = conn.execute(
            """
            SELECT COALESCE(SUM(cash_delta_cents), 0) AS c_sum,
                   COALESCE(SUM(promo_delta_cents), 0) AS p_sum
            FROM wallet_ledger
            WHERE tenant_id = ?
            """,
            (tid,),
        ).fetchone()
        c_led = int(sums["c_sum"] or 0)
        p_led = int(sums["p_sum"] or 0)
        if c_bal != c_led or p_bal != p_led:
            ledger_drifts.append({
                "tenant_id": tid,
                "wallet_cash": c_bal,
                "ledger_cash": c_led,
                "wallet_promo": p_bal,
                "ledger_promo": p_led,
            })

    return {
        "checked_wallets": len(wallets),
        "negative_wallet_count": len(negative_wallets),
        "negative_wallets": negative_wallets,
        "ledger_drift_count": len(ledger_drifts),
        "ledger_drifts": ledger_drifts,
    }


def audit_closed_period_seals(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """核查所有已封账（CLOSED）会计期间的归档总额与当前非作废账单汇总是否严丝合缝。"""
    periods = conn.execute("SELECT * FROM accounting_periods WHERE status = 'CLOSED' ORDER BY period_key ASC").fetchall()
    results: List[Dict[str, Any]] = []
    for p in periods:
        pk = p["period_key"]
        invs = conn.execute("SELECT * FROM invoices WHERE period_key = ? AND status != 'VOID'", (pk,)).fetchall()
        live_sum = sum(parse_legacy_amount_cents(dict(r), "total_cents") for r in invs)
        archived = int(p["archived_total_cents"] or 0)
        results.append({
            "period_key": pk,
            "archived_total_cents": archived,
            "live_invoice_sum_cents": live_sum,
            "delta_cents": live_sum - archived,
            "seal_intact": live_sum == archived,
        })
    return results
