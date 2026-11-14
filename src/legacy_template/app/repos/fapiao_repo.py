# -*- coding: utf-8 -*-
"""增值税数电发票（普票/专票/红字冲销单）数据访问仓储。"""
import sqlite3
from typing import Any, Dict, List, Optional


def insert_fapiao_request(conn: sqlite3.Connection, record: Dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO fapiao_requests (
            id, tenant_id, invoice_id, fapiao_type, buyer_tax_id, title,
            net_amount_cents, tax_amount_cents, gross_amount_cents, sheet_count,
            status, red_letter_of, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record["id"],
            record["tenant_id"],
            record["invoice_id"],
            record.get("fapiao_type", "VAT_SPECIAL_E"),
            record["buyer_tax_id"],
            record["title"],
            int(record["net_amount_cents"]),
            int(record["tax_amount_cents"]),
            int(record["gross_amount_cents"]),
            int(record.get("sheet_count", 1)),
            record.get("status", "ISSUED"),
            record.get("red_letter_of"),
            record["created_at"],
        ),
    )


def get_fapiao_by_id(conn: sqlite3.Connection, fapiao_id: str) -> Optional[Dict[str, Any]]:
    row = conn.execute("SELECT * FROM fapiao_requests WHERE id = ?", (fapiao_id,)).fetchone()
    return dict(row) if row else None


def find_active_fapiao_for_invoice(conn: sqlite3.Connection, invoice_id: str) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        "SELECT * FROM fapiao_requests WHERE invoice_id = ? AND status = 'ISSUED' AND red_letter_of IS NULL LIMIT 1",
        (invoice_id,),
    ).fetchone()
    return dict(row) if row else None


def list_tenant_fapiaos(conn: sqlite3.Connection, tenant_id: str) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM fapiao_requests WHERE tenant_id = ? ORDER BY created_at DESC",
        (tenant_id,),
    ).fetchall()
    return [dict(r) for r in rows]
