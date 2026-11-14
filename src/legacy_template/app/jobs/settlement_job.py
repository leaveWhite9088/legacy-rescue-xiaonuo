# -*- coding: utf-8 -*-
"""周期到期出账批处理与钱包自动扣款结算任务。"""
from datetime import datetime, timedelta, timezone
import sqlite3
import uuid
from typing import Any, Dict

from app.domain.ledger import pay_invoice_from_wallet
from app.domain.pricing import calculate_cycle_bill
from app.infra.logger import get_logger
from app.repos.billing_repo import insert_invoice_with_lines
from app.repos.subscription_repo import list_due_subscriptions

log = get_logger("yunce.jobs.settlement")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def generate_due_cycle_invoices(
    conn: sqlite3.Connection,
    as_of_iso: str,
) -> Dict[str, Any]:
    """扫描到期订阅并生成新周期账单。"""
    subs = list_due_subscriptions(conn, as_of_iso)
    created_ids = []
    now = _now_iso()

    for sub in subs:
        tenant_id = sub["tenant_id"]
        period_key = sub["cycle_end"][:7]
        bill = calculate_cycle_bill(conn, tenant_id, period_key, sub["plan_code"])

        inv_id = f"INV-{period_key.replace('-', '')}-{uuid.uuid4().hex[:6].upper()}"
        lines = [
            {"line_type": "BASE_FEE", "description": f"{sub['plan_code']} 周期订阅费", "quantity": 1, "amount_cents": bill["base_fee_cents"]},
        ]
        if bill["overage_fee_cents"] > 0:
            lines.append({"line_type": "OVERAGE", "description": "阶梯超额调用费", "quantity": 1, "amount_cents": bill["overage_fee_cents"]})
        if bill["tax_cents"] > 0:
            lines.append({"line_type": "TAX", "description": "价外增值税/GST", "quantity": 1, "amount_cents": bill["tax_cents"]})

        insert_invoice_with_lines(
            conn,
            {
                "id": inv_id,
                "tenant_id": tenant_id,
                "period_key": period_key,
                "cycle_start": sub["cycle_start"],
                "cycle_end": sub["cycle_end"],
                "plan_code": sub["plan_code"],
                "base_fee_cents": bill["base_fee_cents"],
                "overage_fee_cents": bill["overage_fee_cents"],
                "tax_cents": bill["tax_cents"],
                "late_fee_cents": 0,
                "total_cents": bill["total_cents"],
                "status": "OPEN",
                "created_at": now,
                "updated_at": now,
            },
            lines,
        )

        try:
            old_end = datetime.fromisoformat(sub["cycle_end"].replace("Z", "+00:00"))
        except Exception:
            old_end = datetime.now(timezone.utc)
        new_start = old_end.strftime("%Y-%m-%dT%H:%M:%SZ")
        new_end = (old_end + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn.execute(
            """
            UPDATE subscriptions
            SET cycle_start = ?, cycle_end = ?, next_billing_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (new_start, new_end, new_end, now, sub["id"]),
        )
        created_ids.append(inv_id)

    return {"created_count": len(created_ids), "invoice_ids": created_ids}


def settle_open_invoices(conn: sqlite3.Connection) -> Dict[str, Any]:
    """扫描 OPEN 账单并尝试从钱包自动扣款结算。"""
    open_invs = conn.execute(
        "SELECT * FROM invoices WHERE status = 'OPEN' ORDER BY created_at ASC"
    ).fetchall()

    settled = 0
    failed = 0
    now = _now_iso()

    for inv in open_invs:
        inv_id = inv["id"]
        conn.execute(
            "UPDATE invoices SET status = 'PENDING_SETTLE', updated_at = ? WHERE id = ?",
            (now, inv_id),
        )
        try:
            pay_invoice_from_wallet(conn, inv_id, inv["tenant_id"], idempotency_key=f"auto:{inv_id}")
            settled += 1
        except Exception as exc:
            log.error("settlement_job: error on inv=%s err=%s", inv_id, exc)
            failed += 1

    return {"settled": settled, "failed": failed}
