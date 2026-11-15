# -*- coding: utf-8 -*-
"""钱包资金账本、赠送金批次核销、账单支付与退款冲正引擎。"""
from datetime import datetime, timezone
import sqlite3
import uuid
from typing import Any, Dict, Optional

from app.compat.wallet_bridge import compute_refund_bucket_split
from app.infra.events import event_bus
from app.infra.logger import get_logger
from app.repos.billing_repo import get_invoice
from app.repos.dunning_repo import resolve_dunning_for_invoice
from app.repos.wallet_repo import append_wallet_ledger, get_wallet_row

log = get_logger("yunce.ledger")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_wallet(conn: sqlite3.Connection, tenant_id: str) -> Dict[str, Any]:
    return get_wallet_row(conn, tenant_id)


def topup_cash(
    conn: sqlite3.Connection,
    tenant_id: str,
    amount_cents: int,
    ref_id: str = "",
    note: str = "现金充值",
) -> Dict[str, Any]:
    if amount_cents <= 0:
        raise ValueError("充值金额必须大于 0")
    now = _now_iso()
    conn.execute(
        "UPDATE wallets SET cash_balance_cents = cash_balance_cents + ?, updated_at = ? WHERE tenant_id = ?",
        (amount_cents, now, tenant_id),
    )
    append_wallet_ledger(conn, tenant_id, "TOPUP", amount_cents, 0, ref_id, note, now)
    return get_wallet(conn, tenant_id)


def grant_promo_credit(
    conn: sqlite3.Connection,
    tenant_id: str,
    amount_cents: int,
    expires_at: str,
    campaign_code: str = "OPS_GRANT",
    note: str = "运营赠送金",
) -> Dict[str, Any]:
    if amount_cents <= 0:
        raise ValueError("赠送金金额必须大于 0")
    now = _now_iso()
    grant_id = f"pg_{uuid.uuid4().hex[:12]}"
    conn.execute(
        """
        INSERT INTO promo_grants (id, tenant_id, initial_cents, remaining_cents, status, expires_at, campaign_code, created_at)
        VALUES (?, ?, ?, ?, 'ACTIVE', ?, ?, ?)
        """,
        (grant_id, tenant_id, amount_cents, amount_cents, expires_at, campaign_code, now),
    )
    conn.execute(
        "UPDATE wallets SET promo_balance_cents = promo_balance_cents + ?, updated_at = ? WHERE tenant_id = ?",
        (amount_cents, now, tenant_id),
    )
    append_wallet_ledger(conn, tenant_id, "PROMO_GRANT", 0, amount_cents, grant_id, note, now)
    return {"grant_id": grant_id, "wallet": get_wallet(conn, tenant_id)}


def pay_invoice_from_wallet(
    conn: sqlite3.Connection,
    invoice_id: str,
    tenant_id: str,
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    """从租户钱包扣款支付账单（优先抵扣赠送金，不足部分扣除现金）。"""
    inv = get_invoice(conn, invoice_id)
    if not inv:
        raise ValueError(f"Invoice not found: {invoice_id}")
    if inv["tenant_id"] != tenant_id:
        raise PermissionError("无权支付其他租户的账单")

    if inv["status"] not in ("OPEN", "PENDING_SETTLE"):
        raise ValueError(f"当前账单状态不允许支付: {inv['status']}")

    if idempotency_key:
        dup = conn.execute(
            "SELECT * FROM invoice_payments WHERE idempotency_key = ? LIMIT 1",
            (idempotency_key,),
        ).fetchone()
        if dup:
            return {
                "payment_id": dup["id"],
                "invoice_id": dup["invoice_id"],
                "cash_paid_cents": dup["cash_paid_cents"],
                "promo_paid_cents": dup["promo_paid_cents"],
                "total_paid_cents": dup["total_paid_cents"],
                "status": "PAID",
            }

    due_cents = int(inv["total_cents"]) - int(inv["paid_cents"])
    if due_cents <= 0:
        return {"invoice_id": invoice_id, "status": inv["status"], "paid_cents": 0}

    wallet = get_wallet(conn, tenant_id)
    avail_promo = max(0, int(wallet["promo_balance_cents"]))
    avail_cash = max(0, int(wallet["cash_balance_cents"]))
    if avail_promo + avail_cash < due_cents:
        raise ValueError("钱包余额不足")

    promo_used = min(avail_promo, due_cents)
    cash_used = due_cents - promo_used
    now = _now_iso()

    rem_to_consume = promo_used
    if rem_to_consume > 0:
        grants = conn.execute(
            "SELECT * FROM promo_grants WHERE tenant_id = ? AND status = 'ACTIVE' AND remaining_cents > 0 ORDER BY expires_at DESC",
            (tenant_id,),
        ).fetchall()
        for g in grants:
            if rem_to_consume <= 0:
                break
            take = min(rem_to_consume, int(g["remaining_cents"]))
            new_rem = int(g["remaining_cents"]) - take
            new_status = "EXHAUSTED" if new_rem == 0 else "ACTIVE"
            conn.execute(
                "UPDATE promo_grants SET remaining_cents = ?, status = ? WHERE id = ?",
                (new_rem, new_status, g["id"]),
            )
            rem_to_consume -= take

    conn.execute(
        """
        UPDATE wallets
        SET cash_balance_cents = cash_balance_cents - ?,
            promo_balance_cents = promo_balance_cents - ?,
            updated_at = ?
        WHERE tenant_id = ?
        """,
        (cash_used, promo_used, now, tenant_id),
    )

    pay_id = f"pay_{uuid.uuid4().hex[:12]}"
    conn.execute(
        """
        INSERT INTO invoice_payments (id, invoice_id, tenant_id, idempotency_key, cash_paid_cents, promo_paid_cents, total_paid_cents, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (pay_id, invoice_id, tenant_id, idempotency_key, cash_used, promo_used, due_cents, now),
    )
    append_wallet_ledger(
        conn, tenant_id, "INVOICE_PAY", -cash_used, -promo_used, invoice_id, f"支付账单 {invoice_id}", now
    )
    conn.execute(
        "UPDATE invoices SET paid_cents = paid_cents + ?, status = 'PAID', updated_at = ? WHERE id = ?",
        (due_cents, now, invoice_id),
    )
    resolve_dunning_for_invoice(conn, invoice_id, now)
    event_bus.publish("invoice.paid", {"invoice_id": invoice_id, "tenant_id": tenant_id, "amount_cents": due_cents})
    return {
        "payment_id": pay_id,
        "invoice_id": invoice_id,
        "cash_paid_cents": cash_used,
        "promo_paid_cents": promo_used,
        "total_paid_cents": due_cents,
        "status": "PAID",
    }


def refund_to_wallet(
    conn: sqlite3.Connection,
    invoice_id: str,
    refund_cents: int,
    reason: str = "账单退款",
) -> Dict[str, Any]:
    """对已支付账单执行部分或全额退款回充（调用 wallet_bridge 计算退回分桶）。"""
    if refund_cents <= 0:
        raise ValueError("退款金额必须大于 0")
    inv = get_invoice(conn, invoice_id)
    if not inv:
        raise ValueError(f"Invoice not found: {invoice_id}")

    refundable = int(inv["paid_cents"]) - int(inv["refunded_cents"])
    if refund_cents > refundable:
        raise ValueError(f"退款金额超过可退上限: refundable={refundable}")

    now = _now_iso()
    tenant_id = inv["tenant_id"]

    split = compute_refund_bucket_split(conn, invoice_id, refund_cents)
    cash_back = int(split["cash_refund_cents"])
    promo_back = int(split["promo_refund_cents"])

    conn.execute(
        """
        UPDATE wallets
        SET cash_balance_cents = cash_balance_cents + ?,
            promo_balance_cents = promo_balance_cents + ?,
            updated_at = ?
        WHERE tenant_id = ?
        """,
        (cash_back, promo_back, now, tenant_id),
    )
    append_wallet_ledger(conn, tenant_id, "REFUND", cash_back, promo_back, invoice_id, reason, now)

    new_refunded = int(inv["refunded_cents"]) + refund_cents
    new_status = "REFUNDED" if new_refunded >= int(inv["paid_cents"]) else inv["status"]
    conn.execute(
        "UPDATE invoices SET refunded_cents = ?, status = ?, updated_at = ? WHERE id = ?",
        (new_refunded, new_status, now, invoice_id),
    )
    event_bus.publish(
        "invoice.refunded",
        {
            "invoice_id": invoice_id,
            "tenant_id": tenant_id,
            "refund_cents": refund_cents,
            "cash_refunded_cents": cash_back,
            "promo_refunded_cents": promo_back,
        },
    )
    return {
        "invoice_id": invoice_id,
        "refund_cents": refund_cents,
        "cash_refunded_cents": cash_back,
        "promo_refunded_cents": promo_back,
        "status": new_status,
    }


def expire_promo_grants(conn: sqlite3.Connection, as_of_iso: Optional[str] = None) -> Dict[str, Any]:
    """清理已到期的运营赠送金批次。"""
    cutoff = as_of_iso or _now_iso()
    rows = conn.execute(
        "SELECT * FROM promo_grants WHERE expires_at <= ?",
        (cutoff,),
    ).fetchall()
    expired_count = 0
    total_deducted = 0
    for g in rows:
        deduct = int(g["initial_cents"])
        conn.execute(
            "UPDATE wallets SET promo_balance_cents = promo_balance_cents - ?, updated_at = ? WHERE tenant_id = ?",
            (deduct, cutoff, g["tenant_id"]),
        )
        conn.execute(
            "UPDATE promo_grants SET status = 'EXPIRED', remaining_cents = 0 WHERE id = ?",
            (g["id"],),
        )
        append_wallet_ledger(conn, g["tenant_id"], "PROMO_EXPIRE", 0, -deduct, g["id"], "赠送金到期清零", cutoff)
        expired_count += 1
        total_deducted += deduct
    return {"expired_count": expired_count, "total_deducted_cents": total_deducted}
