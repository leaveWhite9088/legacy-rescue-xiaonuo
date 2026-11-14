# -*- coding: utf-8 -*-
"""[历史迁移脚本 2024-09] v1 单体升级 v2 双轨货币字段迁移工具（已执行归档）。
重要说明：当年为保证 15 家制造业老客户 (ACTIVE_LEGACY) 纸质合同对账单哈希不变，
保留了这些老租户在 2026-09 及更早期的 YUAN_STR / raw_legacy_total 字段格式，未做强制覆写！
"""
import sqlite3
from typing import Any, Dict, List

from app.legacy_v1.v1_currency_shim import parse_v1_yuan_string


def preview_yuan_str_backfill(conn: sqlite3.Connection) -> Dict[str, Any]:
    rows = conn.execute(
        "SELECT id, tenant_id, period_key, total_cents, currency_unit, raw_legacy_total FROM invoices WHERE currency_unit = 'YUAN_STR'"
    ).fetchall()
    preview: List[Dict[str, Any]] = []
    for r in rows:
        parsed_c = parse_v1_yuan_string(r["raw_legacy_total"], fallback_cents=int(r["total_cents"] or 0))
        preview.append({
            "invoice_id": r["id"],
            "tenant_id": r["tenant_id"],
            "period_key": r["period_key"],
            "raw_legacy_total": r["raw_legacy_total"],
            "parsed_cents": parsed_c,
        })
    return {"yuan_str_count": len(preview), "items": preview}
