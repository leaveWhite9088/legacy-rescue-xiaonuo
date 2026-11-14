# -*- coding: utf-8 -*-
"""2024 纯文本固定列宽客户月结对账单打印器（供传统制造业传真/邮件附件归档使用）。"""
import sqlite3
from typing import List

from app.legacy_v1.v1_currency_shim import (
    format_v1_yuan_display,
    legacy_cent_checksum,
    parse_v1_yuan_string,
)


def render_tenant_ascii_statement_v1(conn: sqlite3.Connection, tenant_id: str, period_key: str) -> str:
    t = conn.execute("SELECT * FROM tenants WHERE id = ?", (tenant_id,)).fetchone()
    if not t:
        raise LookupError(f"Tenant missing: {tenant_id}")

    invs = conn.execute(
        "SELECT * FROM invoices WHERE tenant_id = ? AND period_key = ? ORDER BY id ASC",
        (tenant_id, period_key),
    ).fetchall()
    w = conn.execute("SELECT * FROM wallets WHERE tenant_id = ?", (tenant_id,)).fetchone()

    border = "=" * 78
    thin = "-" * 78
    lines: List[str] = [
        border,
        f"YUNCE CLOUD BILLING STATEMENT (LEGACY V1 FORMAT)    PERIOD: {period_key}",
        thin,
        f"TENANT ID : {t['id']:<24} STATUS : {t['status']}",
        f"CUSTOMER  : {t['company_name']}",
        thin,
        f"{'INVOICE ID':<20} {'PLAN':<16} {'BASE':>10} {'OVERAGE':>10} {'TOTAL':>11} {'STATUS':>7}",
        thin,
    ]

    grand_total = 0
    for inv in invs:
        d = dict(inv)
        tot = parse_v1_yuan_string(d.get("raw_legacy_total"), int(d.get("total_cents") or 0))
        if d["status"] != "VOID":
            grand_total += tot
        lines.append(
            f"{d['id']:<20} {d['plan_code']:<16} "
            f"{format_v1_yuan_display(int(d['base_fee_cents']), False):>10} "
            f"{format_v1_yuan_display(int(d['overage_fee_cents']), False):>10} "
            f"{format_v1_yuan_display(tot, False):>11} "
            f"{d['status']:>7}"
        )

    cash_c = int(w["cash_balance_cents"]) if w else 0
    promo_c = int(w["promo_balance_cents"]) if w else 0
    chk = legacy_cent_checksum(tenant_id, period_key, grand_total)

    lines.extend([
        thin,
        f"ACTIVE PERIOD TOTAL : {format_v1_yuan_display(grand_total)} (EXCLUDING VOID)",
        f"WALLET SNAPSHOT     : CASH={format_v1_yuan_display(cash_c)} | PROMO={format_v1_yuan_display(promo_c)}",
        f"AUDIT CHECKSUM      : {chk}",
        border,
    ])
    return "\n".join(lines)
