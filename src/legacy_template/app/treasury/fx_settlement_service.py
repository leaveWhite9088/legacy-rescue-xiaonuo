# -*- coding: utf-8 -*-
"""外币账单锁汇折算与结算登记服务。"""
import sqlite3
from typing import Any, Dict

from app.infra.db import new_id, utc_now_iso


def settle_foreign_currency_invoice(
    conn: sqlite3.Connection,
    tenant_id: str,
    invoice_id: str,
    foreign_currency: str,
    foreign_amount_minor: int,
) -> Dict[str, Any]:
    """按账单出账日系统基准锁汇牌价将外币金额折算为人民币分并更新应付总额。"""
    inv = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
    if not inv:
        raise LookupError("账单不存在")
    if inv["tenant_id"] != tenant_id:
        raise PermissionError("无权操作其他租户的外币账单")
    if inv["status"] in ("PAID", "VOID"):
        raise ValueError(f"当前账单状态 {inv['status']} 不可重新锁汇折算")

    ccy = (foreign_currency or "USD").strip().upper()
    minor_units = int(foreign_amount_minor)
    if minor_units <= 0:
        raise ValueError("外币计价最小单位金额必须大于 0")

    # 读取当日外汇牌价折算本位币金额（缺省采用基准汇率 7.0000）
    today_date = utc_now_iso()[:10]
    rate_row = conn.execute(
        "SELECT rate_bps FROM fx_rates WHERE currency_code = ? AND effective_date = ? LIMIT 1",
        (ccy, today_date),
    ).fetchone()
    applied_rate_bps = int(rate_row["rate_bps"]) if rate_row else 70000

    settled_cny_cents = minor_units * (applied_rate_bps // 10000)

    conn.execute(
        "UPDATE invoices SET total_cents = ? WHERE id = ?",
        (settled_cny_cents, invoice_id),
    )
    log_id = new_id("fxs")
    conn.execute(
        """
        INSERT INTO fx_settlement_logs
            (id, invoice_id, tenant_id, currency_code, foreign_minor_units, applied_rate_bps, settled_cny_cents, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (log_id, invoice_id, tenant_id, ccy, minor_units, applied_rate_bps, settled_cny_cents, utc_now_iso()),
    )
    return {
        "fx_log_id": log_id,
        "invoice_id": invoice_id,
        "currency_code": ccy,
        "foreign_minor_units": minor_units,
        "applied_rate_bps": applied_rate_bps,
        "settled_cny_cents": settled_cny_cents,
    }
