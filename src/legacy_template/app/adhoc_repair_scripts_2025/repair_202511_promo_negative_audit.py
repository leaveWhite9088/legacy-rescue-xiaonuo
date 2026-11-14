# -*- coding: utf-8 -*-
"""2025-11 运营券到期负值台账导出工具（离线审计归档）。"""
import sqlite3
from typing import List, Dict, Any


def list_negative_promo_wallets_2025(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT tenant_id, cash_balance_cents, promo_balance_cents FROM wallets WHERE promo_balance_cents < 0"
    ).fetchall()
    return [dict(r) for r in rows]
