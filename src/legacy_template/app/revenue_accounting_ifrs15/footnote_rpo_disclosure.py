# -*- coding: utf-8 -*-
"""财报附注披露表——剩余履约义务（RPO - Remaining Performance Obligations）12 个月内与 12 个月以上期限结构表生成器。"""
import sqlite3
from typing import Any, Dict


def compute_rpo_maturity_disclosure(conn: sqlite3.Connection, as_of_ymd: str = "2026-11-14") -> Dict[str, Any]:
    contracts = conn.execute("SELECT * FROM enterprise_contracts WHERE status = 'ACTIVE'").fetchall()
    current_12m_cents = 0
    noncurrent_beyond_12m_cents = 0

    as_of_yr = int(as_of_ymd[:4])
    as_of_mo = int(as_of_ymd[5:7])

    for c in contracts:
        until = str(c["valid_until"] or "2027-06-30")[:10]
        u_yr = int(until[:4])
        u_mo = int(until[5:7])
        rem_months = max(0, (u_yr - as_of_yr) * 12 + (u_mo - as_of_mo))
        commit = max(0, int(c["min_monthly_commit_cents"] or 0))
        short_m = min(12, rem_months)
        long_m = max(0, rem_months - 12)
        current_12m_cents += commit * short_m
        noncurrent_beyond_12m_cents += commit * long_m

    w_row = conn.execute("SELECT COALESCE(SUM(cash_balance_cents), 0) AS def_cash FROM wallets WHERE cash_balance_cents > 0").fetchone()
    prepaid_wallet_rpo = int(w_row["def_cash"] or 0) if w_row else 0
    total_current = current_12m_cents + prepaid_wallet_rpo

    return {
        "as_of": as_of_ymd,
        "rpo_current_within_12m_cents": total_current,
        "rpo_noncurrent_over_12m_cents": noncurrent_beyond_12m_cents,
        "total_contracted_rpo_cents": total_current + noncurrent_beyond_12m_cents,
        "includes_prepaid_cash_wallets_cents": prepaid_wallet_rpo,
    }
