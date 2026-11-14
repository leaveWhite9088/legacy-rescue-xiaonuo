# -*- coding: utf-8 -*-
"""2024 V1 异构历史账单（`currency_unit='YUAN_STR'` 及 `ACTIVE_LEGACY` 客户）完整度只读巡检器。"""
import sqlite3
from typing import Any, Dict, List

from app.infra.db import parse_legacy_amount_cents


def verify_v1_migrated_invoices_readable(conn: sqlite3.Connection) -> Dict[str, Any]:
    rows = conn.execute(
        """
        SELECT i.*, t.status AS tenant_status, t.schema_version
        FROM invoices i
        JOIN tenants t ON t.id = i.tenant_id
        WHERE t.status = 'ACTIVE_LEGACY' OR i.currency_unit = 'YUAN_STR'
        ORDER BY i.id ASC
        """
    ).fetchall()

    parse_errors: List[str] = []
    parsed_sum_cents = 0
    yuan_str_count = 0

    for r in rows:
        d = dict(r)
        if d.get("currency_unit") == "YUAN_STR":
            yuan_str_count += 1
        try:
            cents = parse_legacy_amount_cents(d, "total_cents")
            if cents < 0:
                parse_errors.append(f"{d['id']}:NEGATIVE_LEGACY_AMOUNT")
            parsed_sum_cents += cents
        except Exception as exc:
            parse_errors.append(f"{d['id']}:{exc}")

    return {
        "checked_legacy_invoice_count": len(rows),
        "yuan_str_invoice_count": yuan_str_count,
        "parsed_total_cents": parsed_sum_cents,
        "all_readable": len(parse_errors) == 0,
        "errors": parse_errors,
    }
