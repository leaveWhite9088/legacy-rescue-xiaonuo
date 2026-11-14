# -*- coding: utf-8 -*-
"""v3 钱包分布式 Saga 编排器草稿（实验未投产代码，生产扣款与退款请查看 app.domain.ledger）。"""
from datetime import datetime, timezone
import sqlite3
from typing import Any, Dict

from app.v3_pipeline.commands import (
    SagaExecutionJournal,
    WalletSagaPayCommand,
    WalletSagaRefundCommand,
)


class WalletSagaCoordinatorV3:
    """v3 双阶段预留扣款草稿：依赖尚未建表的 wallet_reservations_v3，线上未启用。"""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def run_pay_saga(self, cmd: WalletSagaPayCommand) -> Dict[str, Any]:
        journal = SagaExecutionJournal(saga_id=cmd.saga_id, command_type="PAY_INVOICE")
        inv = self.conn.execute("SELECT * FROM invoices WHERE id = ?", (cmd.invoice_id,)).fetchone()
        if not inv:
            journal.aborted_reason = "INVOICE_NOT_FOUND"
            return {"committed": False, "journal": journal}

        journal.append_step("LOAD_INVOICE", "COMPLETED", invoice_status=inv["status"])
        w = self.conn.execute("SELECT * FROM wallets WHERE tenant_id = ?", (cmd.tenant_id,)).fetchone()
        if not w:
            journal.aborted_reason = "WALLET_NOT_FOUND"
            return {"committed": False, "journal": journal}

        due = max(0, int(inv["total_cents"]) - int(inv["paid_cents"]))
        promo_cap = max(0, int(w["promo_balance_cents"])) if cmd.prefer_promo_first else 0
        promo_take = min(promo_cap, due)
        cash_take = due - promo_take
        if int(w["cash_balance_cents"]) < cash_take:
            journal.aborted_reason = "INSUFFICIENT_FUNDS"
            return {"committed": False, "journal": journal}

        # v3 预留表尚未在生产库迁移创建，因此仅返回试算日志
        journal.append_step(
            "SIMULATE_RESERVATION",
            "COMPLETED",
            promo_take=str(promo_take),
            cash_take=str(cash_take),
        )
        return {
            "committed": True,
            "simulated_only": True,
            "promo_reserved_cents": promo_take,
            "cash_reserved_cents": cash_take,
            "completed_at": self._now(),
        }

    def run_refund_saga(self, cmd: WalletSagaRefundCommand) -> Dict[str, Any]:
        journal = SagaExecutionJournal(saga_id=cmd.saga_id, command_type="REFUND_INVOICE")
        pays = self.conn.execute(
            "SELECT COALESCE(SUM(cash_paid_cents),0) AS c, COALESCE(SUM(promo_paid_cents),0) AS p FROM invoice_payments WHERE invoice_id = ?",
            (cmd.invoice_id,),
        ).fetchone()
        c_max = int(pays["c"]) if pays else 0
        c_ref = min(cmd.requested_refund_cents, c_max)
        p_ref = cmd.requested_refund_cents - c_ref
        journal.append_step("SPLIT_REFUND_BUCKETS", "COMPLETED", cash=str(c_ref), promo=str(p_ref))
        return {
            "committed": True,
            "simulated_only": True,
            "cash_refund_preview_cents": c_ref,
            "promo_refund_preview_cents": p_ref,
        }
