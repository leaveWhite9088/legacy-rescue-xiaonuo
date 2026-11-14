# -*- coding: utf-8 -*-
"""[历史迁移脚本 2025-01] 单一余额钱包拆分为现金池 (cash_balance_cents) 与赠送金池 (promo_balance_cents)。
当时的遗留已知局限：拆分上线时，为了赶双十一后财务月结窗口，wallet_bridge.compute_refund_bucket_split
曾临时加了 legacy_fast_cash_mode=True 开关，预定 2025 Q2 补齐按实付比例拆退但一直被搁置。
"""
import sqlite3
from typing import Any, Dict


def verify_dual_wallet_schema(conn: sqlite3.Connection) -> Dict[str, Any]:
    cols = [r[1] for r in conn.execute("PRAGMA table_info(wallets)").fetchall()]
    grant_cnt = conn.execute("SELECT COUNT(*) FROM promo_grants").fetchone()[0]
    return {
        "has_cash_col": "cash_balance_cents" in cols,
        "has_promo_col": "promo_balance_cents" in cols,
        "promo_grants_count": grant_cnt,
    }
