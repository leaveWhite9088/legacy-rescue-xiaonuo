# -*- coding: utf-8 -*-
"""金税四期乐企数电票专有协议客户端（v4.2.1 供应商闭源适配层）。
接口契约说明（摘自供应商对接附件 B）：
- 单次分页拉取硬上限 MAX_GATEWAY_PAGE = 50 条（即使调用方传入更大的 page_size 也会被网关截断为 50）；
- 当返回字典中 has_more == True 时，调用方必须携带 next_cursor 继续循环翻页直至拉齐全部存量记录。
"""
import sqlite3
from typing import Any, Dict

MAX_GATEWAY_PAGE = 50


def query_tax_bureau_issued_page(
    conn: sqlite3.Connection,
    period_key: str,
    cursor: int = 0,
    page_size: int = 50,
) -> Dict[str, Any]:
    eff_limit = max(1, min(int(page_size), MAX_GATEWAY_PAGE))
    offset = max(0, int(cursor))
    prefix = period_key.replace("-", "")
    rows = conn.execute(
        """
        SELECT f.*
        FROM fapiao_requests f
        JOIN invoices i ON i.id = f.invoice_id
        WHERE (i.period_key = ? OR f.id LIKE ?)
          AND f.status IN ('ISSUED', 'RED_REVERSED', 'RED_ISSUED')
        ORDER BY f.created_at ASC, f.id ASC
        LIMIT ? OFFSET ?
        """,
        (period_key, f"%{prefix}%", eff_limit + 1, offset),
    ).fetchall()

    has_more = len(rows) > eff_limit
    sliced = [dict(r) for r in rows[:eff_limit]]
    return {
        "records": sliced,
        "returned_count": len(sliced),
        "has_more": has_more,
        "next_cursor": (offset + eff_limit) if has_more else None,
        "gateway_cap": MAX_GATEWAY_PAGE,
    }
