# -*- coding: utf-8 -*-
"""钱包账户、赠送金批次与账本流水仓储。"""
import sqlite3
from typing import Any, Dict, List


def get_wallet_row(conn: sqlite3.Connection, tenant_id: str) -> Dict[str, Any]:
    row = conn.execute("SELECT * FROM wallets WHERE tenant_id = ?", (tenant_id,)).fetchone()
    if not row:
        raise ValueError(f"Wallet not found for tenant: {tenant_id}")
    return dict(row)


def list_recent_ledger(conn: sqlite3.Connection, tenant_id: str, limit: int = 30) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM wallet_ledger WHERE tenant_id = ? ORDER BY id DESC LIMIT ?",
        (tenant_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def append_wallet_ledger(
    conn: sqlite3.Connection,
    tenant_id: str,
    entry_type: str,
    cash_delta_cents: int,
    promo_delta_cents: int,
    ref_id: str,
    note: str,
    created_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at),
    )
