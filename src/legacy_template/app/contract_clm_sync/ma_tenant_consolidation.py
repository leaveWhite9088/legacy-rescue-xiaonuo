# -*- coding: utf-8 -*-
"""客户企业并购（M&A）租户主体合并：历史未结清账单、赠送金与框架保底过户预检工具。"""
import sqlite3
from typing import Any, Dict


def preview_tenant_merger_impact(
    conn: sqlite3.Connection,
    acquirer_tenant_id: str,
    acquired_tenant_id: str,
) -> Dict[str, Any]:
    if acquirer_tenant_id == acquired_tenant_id:
        raise ValueError("并购主存续方与被吸收方不能为同一租户")

    t1 = conn.execute("SELECT * FROM tenants WHERE id = ?", (acquirer_tenant_id,)).fetchone()
    t2 = conn.execute("SELECT * FROM tenants WHERE id = ?", (acquired_tenant_id,)).fetchone()
    if not t1 or not t2:
        raise LookupError("并购任一方租户档案不存在")

    w1 = conn.execute("SELECT * FROM wallets WHERE tenant_id = ?", (acquirer_tenant_id,)).fetchone()
    w2 = conn.execute("SELECT * FROM wallets WHERE tenant_id = ?", (acquired_tenant_id,)).fetchone()

    open_invs_2 = conn.execute(
        "SELECT COUNT(*) AS cnt, COALESCE(SUM(total_cents - paid_cents), 0) AS due FROM invoices WHERE tenant_id = ? AND status IN ('OPEN', 'PENDING_SETTLE', 'PARTIAL_PAID')",
        (acquired_tenant_id,),
    ).fetchone()

    blockers = []
    if t1["tax_profile_code"] != t2["tax_profile_code"]:
        blockers.append(f"税务档案不一致: {t1['tax_profile_code']} vs {t2['tax_profile_code']}")
    if int(w2["promo_balance_cents"] or 0) < 0:
        blockers.append("被吸收方赠送金池存在异常负余额，须先完成账务平账")

    combined_cash = int(w1["cash_balance_cents"] or 0) + int(w2["cash_balance_cents"] or 0)
    combined_promo = max(0, int(w1["promo_balance_cents"] or 0)) + max(0, int(w2["promo_balance_cents"] or 0))

    return {
        "acquirer_tenant_id": acquirer_tenant_id,
        "acquired_tenant_id": acquired_tenant_id,
        "can_auto_merge": len(blockers) == 0,
        "blockers": blockers,
        "combined_cash_cents": combined_cash,
        "combined_promo_cents": combined_promo,
        "transferred_open_invoice_count": int(open_invs_2["cnt"] or 0),
        "transferred_open_receivable_cents": int(open_invs_2["due"] or 0),
    }
