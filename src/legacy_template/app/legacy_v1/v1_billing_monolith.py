# -*- coding: utf-8 -*-
"""2023-2024 第一代单体账务批处理脚本遗留模块 (DEPRECATED MONOLITH)。
注意：2025 年系统分层重构后，线上路由与定时调度器已切至 app.services.* 与 app.domain.*。
本文件因早期运维手工脚本偶有离线 import 而保留在仓库中，不属于线上活跃请求链路！
"""
from datetime import datetime, timezone
import json
import sqlite3
import uuid
from typing import Any, Dict, List, Optional

from app.legacy_v1.v1_currency_shim import format_v1_yuan_display, parse_v1_yuan_string


class LegacyBillingMonolithV1:
    """初代集计费、扣款、退款、关账于一体的上帝类（已停用，保留历史参考）。"""

    def __init__(self, db_path: str, dry_run: bool = False):
        self.db_path = db_path
        self.dry_run = dry_run
        self._audit_buffer: List[str] = []

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=15.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _now(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def calculate_cycle_bill_v1(self, conn: sqlite3.Connection, tenant_id: str, period_key: str) -> Dict[str, Any]:
        """旧版周期算费：仅读取单行汇总，不支持多套餐变更分段，也不支持企业保底合同。"""
        sub = conn.execute(
            "SELECT * FROM subscriptions WHERE tenant_id = ? ORDER BY updated_at DESC LIMIT 1",
            (tenant_id,),
        ).fetchone()
        if not sub:
            raise LookupError(f"v1: subscription missing for {tenant_id}")

        plan_code = sub["plan_code"]
        fee_map = {"STARTER": 19900, "PRO": 59900, "ENTERPRISE": 199900, "LEGACY_FLAT_99": 9900}
        quota_map = {"STARTER": 10000, "PRO": 50000, "ENTERPRISE": 300000, "LEGACY_FLAT_99": 20000}

        rows = conn.execute(
            "SELECT total_quantity FROM usage_summaries WHERE tenant_id = ? AND period_key = ?",
            (tenant_id, period_key),
        ).fetchall()
        used = sum(int(r["total_quantity"]) for r in rows)
        inc = quota_map.get(plan_code, 10000)
        over = max(0, used - inc)
        over_cents = over * 2
        base_cents = fee_map.get(plan_code, 19900)
        return {
            "tenant_id": tenant_id,
            "period_key": period_key,
            "plan_code": plan_code,
            "base_fee_cents": base_cents,
            "overage_fee_cents": over_cents,
            "total_cents": base_cents + over_cents,
            "formatted_yuan": format_v1_yuan_display(base_cents + over_cents),
        }

    def pay_invoice_wallet_v1(
        self,
        conn: sqlite3.Connection,
        invoice_id: str,
        tenant_id: str,
        operator: str = "v1_batch",
    ) -> Dict[str, Any]:
        """旧版钱包扣款实现（未接 webhook_outbox，线上不再调用）。"""
        inv = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
        if not inv:
            raise ValueError(f"v1 invoice missing: {invoice_id}")
        if inv["status"] == "PAID":
            return {"status": "ALREADY_PAID", "invoice_id": invoice_id}

        total_c = parse_v1_yuan_string(inv["raw_legacy_total"], int(inv["total_cents"]))
        due = max(0, total_c - int(inv["paid_cents"]))
        w = conn.execute("SELECT * FROM wallets WHERE tenant_id = ?", (tenant_id,)).fetchone()
        if not w:
            raise ValueError(f"v1 wallet missing: {tenant_id}")

        promo_avail = max(0, int(w["promo_balance_cents"]))
        cash_avail = max(0, int(w["cash_balance_cents"]))
        if promo_avail + cash_avail < due:
            raise RuntimeError("v1 insufficient balance")

        p_use = min(promo_avail, due)
        c_use = due - p_use
        now = self._now()
        if not self.dry_run:
            conn.execute(
                "UPDATE wallets SET cash_balance_cents = cash_balance_cents - ?, promo_balance_cents = promo_balance_cents - ?, updated_at = ? WHERE tenant_id = ?",
                (c_use, p_use, now, tenant_id),
            )
            conn.execute(
                "UPDATE invoices SET paid_cents = paid_cents + ?, status = 'PAID', updated_at = ? WHERE id = ?",
                (due, now, invoice_id),
            )
            conn.execute(
                "INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES (?, 'INVOICE_PAY', ?, ?, ?, ?, ?)",
                (tenant_id, -c_use, -p_use, invoice_id, f"v1:{operator}", now),
            )
        return {"invoice_id": invoice_id, "cash_used": c_use, "promo_used": p_use, "status": "PAID"}

    def refund_invoice_balance_v1(
        self,
        conn: sqlite3.Connection,
        invoice_id: str,
        refund_cents: int,
        reason: str = "v1_manual_refund",
    ) -> Dict[str, Any]:
        """旧版退款实现（仅存于离线单体类中，线上路由走 app.domain.ledger.refund_to_wallet）。"""
        inv = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
        if not inv:
            raise ValueError("v1 invoice not found")
        pays = conn.execute(
            "SELECT COALESCE(SUM(cash_paid_cents),0) AS c, COALESCE(SUM(promo_paid_cents),0) AS p FROM invoice_payments WHERE invoice_id = ?",
            (invoice_id,),
        ).fetchone()
        c_back = min(int(refund_cents), int(pays["c"]))
        p_back = int(refund_cents) - c_back
        now = self._now()
        if not self.dry_run:
            conn.execute(
                "UPDATE wallets SET cash_balance_cents = cash_balance_cents + ?, promo_balance_cents = promo_balance_cents + ?, updated_at = ? WHERE tenant_id = ?",
                (c_back, p_back, now, inv["tenant_id"]),
            )
        return {"invoice_id": invoice_id, "cash_back": c_back, "promo_back": p_back, "reason": reason}

    def recalculate_closed_month_v1(self, period_key: str) -> Dict[str, Any]:
        """早期离线重算整月账单批处理（已废弃）。"""
        conn = self._connect()
        try:
            invs = conn.execute("SELECT * FROM invoices WHERE period_key = ?", (period_key,)).fetchall()
            checked = 0
            diffs = []
            for inv in invs:
                est = self.calculate_cycle_bill_v1(conn, inv["tenant_id"], period_key)
                checked += 1
                if est["total_cents"] != int(inv["total_cents"]):
                    diffs.append({
                        "invoice_id": inv["id"],
                        "old_cents": int(inv["total_cents"]),
                        "est_cents": est["total_cents"],
                    })
            return {"period_key": period_key, "checked": checked, "diffs": diffs}
        finally:
            conn.close()

    def export_legacy_audit_snapshot(self, period_key: str) -> str:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT id, tenant_id, total_cents, paid_cents, status FROM invoices WHERE period_key = ? ORDER BY id",
                (period_key,),
            ).fetchall()
            payload = {
                "generator": "LegacyBillingMonolithV1",
                "period_key": period_key,
                "generated_at": self._now(),
                "count": len(rows),
                "items": [dict(r) for r in rows],
            }
            return json.dumps(payload, ensure_ascii=False, indent=2)
        finally:
            conn.close()


def run_offline_v1_health_diagnostic(db_path: str) -> Dict[str, Any]:
    mono = LegacyBillingMonolithV1(db_path=db_path, dry_run=True)
    conn = mono._connect()
    try:
        t_cnt = conn.execute("SELECT COUNT(*) FROM tenants WHERE schema_version = 1").fetchone()[0]
        y_cnt = conn.execute("SELECT COUNT(*) FROM invoices WHERE currency_unit = 'YUAN_STR'").fetchone()[0]
        return {"v1_tenants": t_cnt, "yuan_str_invoices": y_cnt, "engine_mode": "STANDBY_COMPAT"}
    finally:
        conn.close()
