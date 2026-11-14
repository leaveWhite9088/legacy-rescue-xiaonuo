# -*- coding: utf-8 -*-
"""2025 年终封账归档摘要验算脚本。"""
import hashlib
import sqlite3
from typing import Any, Dict

from app.infra.db import parse_legacy_amount_cents


def compute_closed_period_digest(conn: sqlite3.Connection, period_key: str) -> Dict[str, Any]:
    invs = conn.execute(
        "SELECT id, total_cents, currency_unit, raw_legacy_total, status FROM invoices WHERE period_key = ? AND status != 'VOID' ORDER BY id ASC",
        (period_key,),
    ).fetchall()
    sum_cents = 0
    parts = []
    for r in invs:
        d = dict(r)
        eff = parse_legacy_amount_cents(d, "total_cents")
        sum_cents += eff
        parts.append(f"{r['id']}:{eff}:{r['status']}")
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return {
        "period_key": period_key,
        "invoice_count": len(invs),
        "computed_sum_cents": sum_cents,
        "seal_sha256": digest,
    }
