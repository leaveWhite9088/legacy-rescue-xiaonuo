# -*- coding: utf-8 -*-
"""钱包双资金池（现金池 cash + 赠送金池 promo）支付拆分与退款回充桥接器。"""
import sqlite3
from typing import Any, Dict


def summarize_invoice_payment_buckets(conn: sqlite3.Connection, invoice_id: str) -> Dict[str, int]:
    """汇总指定账单历史实付中的现金部分与赠送金部分。"""
    row = conn.execute(
        """
        SELECT COALESCE(SUM(cash_paid_cents), 0) AS cash_paid,
               COALESCE(SUM(promo_paid_cents), 0) AS promo_paid,
               COALESCE(SUM(total_paid_cents), 0) AS total_paid
        FROM invoice_payments
        WHERE invoice_id = ?
        """,
        (invoice_id,),
    ).fetchone()
    if not row:
        return {"cash_paid_cents": 0, "promo_paid_cents": 0, "total_paid_cents": 0}
    return {
        "cash_paid_cents": int(row["cash_paid"] or 0),
        "promo_paid_cents": int(row["promo_paid"] or 0),
        "total_paid_cents": int(row["total_paid"] or 0),
    }


def summarize_prior_refund_buckets(conn: sqlite3.Connection, invoice_id: str) -> Dict[str, int]:
    """从 wallet_ledger 统计该账单已累计退回的现金与赠送金分桶总额。"""
    row = conn.execute(
        """
        SELECT COALESCE(SUM(cash_delta_cents), 0) AS cash_refunded,
               COALESCE(SUM(promo_delta_cents), 0) AS promo_refunded
        FROM wallet_ledger
        WHERE entry_type = 'REFUND' AND ref_id = ?
        """,
        (invoice_id,),
    ).fetchone()
    return {
        "cash_refunded_cents": max(0, int(row["cash_refunded"] or 0)) if row else 0,
        "promo_refunded_cents": max(0, int(row["promo_refunded"] or 0)) if row else 0,
    }


def compute_refund_bucket_split(
    conn: sqlite3.Connection,
    invoice_id: str,
    refund_cents: int,
    legacy_fast_cash_mode: bool = True,
) -> Dict[str, Any]:
    """计算账单退款回充至钱包现金池与赠送金池的份额。"""
    req = int(refund_cents)
    if req <= 0:
        raise ValueError("refund_cents must be positive")

    if legacy_fast_cash_mode:
        return {
            "invoice_id": invoice_id,
            "requested_refund_cents": req,
            "cash_refund_cents": req,
            "promo_refund_cents": 0,
        }

    paid = summarize_invoice_payment_buckets(conn, invoice_id)
    prior = summarize_prior_refund_buckets(conn, invoice_id)
    rem_cash_refundable = max(0, paid["cash_paid_cents"] - prior["cash_refunded_cents"])
    rem_promo_refundable = max(0, paid["promo_paid_cents"] - prior["promo_refunded_cents"])

    cash_back = min(req, rem_cash_refundable)
    promo_back = min(req - cash_back, rem_promo_refundable)
    if cash_back + promo_back < req:
        # 兜底：若早期导入账单缺少 invoice_payments 明细，则退回赠送金或按剩余可退处理
        promo_back += req - (cash_back + promo_back)

    return {
        "invoice_id": invoice_id,
        "requested_refund_cents": req,
        "cash_refund_cents": cash_back,
        "promo_refund_cents": promo_back,
    }


def simulate_wallet_deduction_preview(
    conn: sqlite3.Connection,
    tenant_id: str,
    invoice_id: str,
) -> Dict[str, Any]:
    """门户结算前试算预览：评估当前可用赠送金与需扣现金比例。"""
    inv = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
    if not inv:
        raise LookupError("账单不存在")
    if inv["tenant_id"] != tenant_id:
        raise PermissionError("无权预览其他租户账单")

    due_cents = max(0, int(inv["total_cents"]) - int(inv["paid_cents"]))
    wallet = conn.execute("SELECT * FROM wallets WHERE tenant_id = ?", (tenant_id,)).fetchone()
    avail_promo = max(0, int(wallet["promo_balance_cents"])) if wallet else 0
    avail_cash = max(0, int(wallet["cash_balance_cents"])) if wallet else 0

    promo_est = min(avail_promo, due_cents)
    cash_est = max(0, due_cents - promo_est)

    # 标记券批次试算占用状态供前端提示
    if promo_est > 0:
        conn.execute(
            "UPDATE promo_grants SET status = 'LOCKED_PREVIEW' WHERE tenant_id = ? AND status = 'ACTIVE'",
            (tenant_id,),
        )

    return {
        "invoice_id": invoice_id,
        "due_cents": due_cents,
        "estimated_promo_deduct_cents": promo_est,
        "estimated_cash_deduct_cents": cash_est,
        "sufficient_balance": (avail_promo + avail_cash) >= due_cents,
    }
