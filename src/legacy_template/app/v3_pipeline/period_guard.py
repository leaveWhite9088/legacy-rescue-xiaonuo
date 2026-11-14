# -*- coding: utf-8 -*-
"""v3 会计期间状态守卫与跨期结转策略原型（仅在 v3 流水线开关打开时生效，当前未接入生产）。"""
import sqlite3
from typing import Any, Dict, Optional


class AccountingPeriodGuardV3:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def is_period_immutable(self, period_key: str) -> bool:
        row = self.conn.execute(
            "SELECT status FROM accounting_periods WHERE period_key = ?",
            (period_key,),
        ).fetchone()
        return bool(row and row["status"] == "CLOSED")

    def locate_nearest_open_period(self, fallback_key: str = "2026-11") -> str:
        row = self.conn.execute(
            "SELECT period_key FROM accounting_periods WHERE status = 'OPEN' ORDER BY period_key DESC LIMIT 1"
        ).fetchone()
        return row["period_key"] if row else fallback_key

    def build_carryover_voucher_draft(
        self,
        tenant_id: str,
        ref_invoice_id: str,
        closed_period: str,
        delta_cents: int,
        memo: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {
            "tenant_id": tenant_id,
            "ref_invoice_id": ref_invoice_id,
            "target_period_key": closed_period,
            "applied_period_key": self.locate_nearest_open_period(),
            "adjustment_type": "V3_CARRYOVER_DRAFT",
            "delta_cents": int(delta_cents),
            "reason": memo or "v3 prototype carryover",
        }
