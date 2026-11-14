# -*- coding: utf-8 -*-
"""影子结算对比器：只读对比钱包可用余额与待结清 OPEN 账单缺口。"""
import sqlite3
from typing import Any, Dict


def build_shadow_settlement_readiness(conn: sqlite3.Connection, period_key: str = "2026-11") -> Dict[str, Any]:
    rows = conn.execute(
        """
        SELECT i.id, i.tenant_id, i.total_cents, i.paid_cents, i.dispute_reason,
               w.cash_balance_cents, w.promo_balance_cents
        FROM invoices i
        LEFT JOIN wallets w ON w.tenant_id = i.tenant_id
        WHERE i.period_key = ? AND i.status = 'OPEN'
        """,
        (period_key,),
    ).fetchall()
    ready = 0
    shortfall_count = 0
    disputed_open = 0
    total_shortfall_cents = 0

    for r in rows:
        if (r["dispute_reason"] or "").strip():
            disputed_open += 1
            continue
        due = max(0, int(r["total_cents"]) - int(r["paid_cents"]))
        avail = max(0, int(r["cash_balance_cents"] or 0)) + max(0, int(r["promo_balance_cents"] or 0))
        if avail >= due:
            ready += 1
        else:
            shortfall_count += 1
            total_shortfall_cents += due - avail

    return {
        "period_key": period_key,
        "open_count": len(rows),
        "ready_to_settle": ready,
        "disputed_frozen": disputed_open,
        "insufficient_wallet_count": shortfall_count,
        "total_shortfall_cents": total_shortfall_cents,
    }
