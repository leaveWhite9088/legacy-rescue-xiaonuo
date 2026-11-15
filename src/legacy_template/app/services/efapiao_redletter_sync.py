# -*- coding: utf-8 -*-
"""数电发票红字信息表回执落库与销项月度汇总服务。"""
from datetime import datetime, timezone
import sqlite3
from typing import Any, Dict, List


def persist_confirmed_red_fapiao_batch(conn: sqlite3.Connection, items: List[Dict[str, Any]]) -> int:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    count = 0
    for item in items:
        orig = conn.execute("SELECT * FROM fapiao_requests WHERE id = ?", (item["original_fapiao_id"],)).fetchone()
        if not orig:
            continue
        conn.execute(
            """INSERT INTO fapiao_requests
               (id, tenant_id, invoice_id, fapiao_type, buyer_tax_id, title,
                net_amount_cents, tax_amount_cents, gross_amount_cents, sheet_count, status, red_letter_of, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'RED_ISSUED', ?, ?)""",
            (
                item["red_fapiao_id"],
                orig["tenant_id"],
                orig["invoice_id"],
                orig["fapiao_type"],
                orig["buyer_tax_id"],
                orig["title"],
                abs(int(orig["net_amount_cents"])),
                abs(int(orig["tax_amount_cents"])),
                abs(int(orig["gross_amount_cents"])),
                orig["id"],
                now,
            ),
        )
        count += 1
    return count
