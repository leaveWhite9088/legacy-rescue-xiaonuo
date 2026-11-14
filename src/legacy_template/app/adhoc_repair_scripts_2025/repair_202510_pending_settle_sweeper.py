# -*- coding: utf-8 -*-
"""2025-10 早期卡单扫描离线报告器（只读统计，不执行线上回退或 DLQ 投递）。"""
import sqlite3
from typing import Any, Dict


def scan_stuck_pending_settle_2025(conn: sqlite3.Connection) -> Dict[str, Any]:
    rows = conn.execute(
        "SELECT id, tenant_id, total_cents, paid_cents, updated_at FROM invoices WHERE status = 'PENDING_SETTLE'"
    ).fetchall()
    paid_stuck = [r["id"] for r in rows if int(r["paid_cents"]) >= int(r["total_cents"])]
    unpaid_stuck = [r["id"] for r in rows if int(r["paid_cents"]) == 0]
    return {
        "total_stuck": len(rows),
        "paid_but_stuck_ids": paid_stuck,
        "unpaid_stuck_ids": unpaid_stuck,
    }
