# -*- coding: utf-8 -*-
"""2024 第一代月末离线轧账与银企直连文本比对批处理模块 (DEPRECATED)。
注意：2025 Q2 起线上正式关账与总账轧差已迁移至 app.domain.reconcile 与 app.services.bank_statement_matcher。
本模块仅保留供财务部历史归档核查脚本离线调用，不在实时 API 链路中执行写操作。
"""
from datetime import datetime, timezone
import hashlib
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from app.legacy_v1.v1_currency_shim import format_v1_yuan_display, parse_v1_yuan_string


class V1MonthEndTrialBalanceRunner:
    """2024 单体架构月末四表核对器（应收单、实收单、钱包快照、手工银行流水）。"""

    def __init__(self, conn: sqlite3.Connection, strict_yuan_mode: bool = False):
        self.conn = conn
        self.strict_yuan_mode = strict_yuan_mode

    @staticmethod
    def _utc_stamp() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def collect_period_invoice_buckets(self, period_key: str) -> Dict[str, Any]:
        rows = self.conn.execute(
            """
            SELECT id, tenant_id, plan_code, base_fee_cents, overage_fee_cents,
                   tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
                   currency_unit, raw_legacy_total, status
            FROM invoices
            WHERE period_key = ?
            ORDER BY id ASC
            """,
            (period_key,),
        ).fetchall()

        by_status: Dict[str, int] = {}
        by_plan: Dict[str, int] = {}
        gross_active_cents = 0
        collected_cents = 0
        refunded_cents = 0
        anomalies: List[Dict[str, Any]] = []

        for r in rows:
            d = dict(r)
            st = str(d["status"] or "UNKNOWN")
            pl = str(d["plan_code"] or "UNKNOWN")
            eff_total = parse_v1_yuan_string(d.get("raw_legacy_total"), int(d.get("total_cents") or 0))
            paid_c = int(d.get("paid_cents") or 0)
            ref_c = int(d.get("refunded_cents") or 0)

            by_status[st] = by_status.get(st, 0) + 1
            if st != "VOID":
                gross_active_cents += eff_total
                by_plan[pl] = by_plan.get(pl, 0) + eff_total
                collected_cents += paid_c
                refunded_cents += ref_c

            component_sum = (
                int(d.get("base_fee_cents") or 0)
                + int(d.get("overage_fee_cents") or 0)
                + int(d.get("tax_cents") or 0)
                + int(d.get("late_fee_cents") or 0)
            )
            if d.get("currency_unit") != "YUAN_STR" and component_sum != eff_total:
                anomalies.append({
                    "invoice_id": d["id"],
                    "tenant_id": d["tenant_id"],
                    "kind": "COMPONENT_MISMATCH",
                    "component_sum_cents": component_sum,
                    "header_total_cents": eff_total,
                })
            if st == "PAID" and paid_c < eff_total:
                anomalies.append({
                    "invoice_id": d["id"],
                    "tenant_id": d["tenant_id"],
                    "kind": "PAID_HEADER_UNDERFUNDED",
                    "paid_cents": paid_c,
                    "effective_total_cents": eff_total,
                })
            if st == "PENDING_SETTLE":
                anomalies.append({
                    "invoice_id": d["id"],
                    "tenant_id": d["tenant_id"],
                    "kind": "STUCK_IN_FLIGHT_SETTLEMENT",
                    "paid_cents": paid_c,
                })

        return {
            "period_key": period_key,
            "generated_at": self._utc_stamp(),
            "status_counts": by_status,
            "plan_revenue_cents": by_plan,
            "gross_active_cents": gross_active_cents,
            "gross_active_yuan": format_v1_yuan_display(gross_active_cents),
            "collected_cents": collected_cents,
            "refunded_cents": refunded_cents,
            "net_collected_cents": collected_cents - refunded_cents,
            "anomalies": anomalies,
        }

    def cross_check_payments_vs_ledger(self, period_key: str) -> Dict[str, Any]:
        """核对 invoice_payments 明细表与 wallet_ledger 扣款流水的双向一致性。"""
        invs = self.conn.execute(
            "SELECT id, tenant_id, paid_cents, status FROM invoices WHERE period_key = ?",
            (period_key,),
        ).fetchall()

        mismatches: List[Dict[str, Any]] = []
        checked = 0
        for inv in invs:
            checked += 1
            iid = inv["id"]
            p_sum = self.conn.execute(
                """
                SELECT COALESCE(SUM(cash_paid_cents), 0) AS c_paid,
                       COALESCE(SUM(promo_paid_cents), 0) AS p_paid,
                       COALESCE(SUM(total_paid_cents), 0) AS t_paid,
                       COUNT(*) AS cnt
                FROM invoice_payments
                WHERE invoice_id = ?
                """,
                (iid,),
            ).fetchone()
            l_sum = self.conn.execute(
                """
                SELECT COALESCE(SUM(-cash_delta_cents), 0) AS c_led,
                       COALESCE(SUM(-promo_delta_cents), 0) AS p_led
                FROM wallet_ledger
                WHERE entry_type = 'INVOICE_PAY' AND ref_id = ?
                """,
                (iid,),
            ).fetchone()

            header_paid = int(inv["paid_cents"] or 0)
            pay_table_tot = int(p_sum["t_paid"] or 0)
            ledger_tot = int(l_sum["c_led"] or 0) + int(l_sum["p_led"] or 0)

            if not (header_paid == pay_table_tot == ledger_tot):
                mismatches.append({
                    "invoice_id": iid,
                    "tenant_id": inv["tenant_id"],
                    "invoice_status": inv["status"],
                    "header_paid_cents": header_paid,
                    "payment_rows_cents": pay_table_tot,
                    "ledger_rows_cents": ledger_tot,
                    "payment_row_count": int(p_sum["cnt"] or 0),
                })

        return {
            "period_key": period_key,
            "checked_invoices": checked,
            "mismatch_count": len(mismatches),
            "mismatches": mismatches,
        }

    def build_archive_seal_hash_v1(self, period_key: str) -> Tuple[str, int]:
        """计算 2024 老版封账防篡改 SHA256 指纹。"""
        rows = self.conn.execute(
            """
            SELECT id, tenant_id, total_cents, currency_unit, raw_legacy_total, status
            FROM invoices
            WHERE period_key = ? AND status != 'VOID'
            ORDER BY id ASC
            """,
            (period_key,),
        ).fetchall()
        digest = hashlib.sha256()
        running_cents = 0
        for r in rows:
            d = dict(r)
            amt = parse_v1_yuan_string(d.get("raw_legacy_total"), int(d.get("total_cents") or 0))
            running_cents += amt
            digest.update(f"{d['id']}:{d['tenant_id']}:{amt}:{d['status']}\n".encode("utf-8"))
        return digest.hexdigest(), running_cents


def parse_v1_fixed_width_bank_txt(raw_lines: List[str]) -> List[Dict[str, Any]]:
    """解析 2024 招商银行离线批导定长回单格式（列宽：日期10 + 流水号18 + 户名30 + 金额12）。"""
    parsed: List[Dict[str, Any]] = []
    for idx, line in enumerate(raw_lines):
        if not line or line.startswith("#") or len(line) < 58:
            continue
        tx_date = line[0:10].strip()
        serial_no = line[10:28].strip()
        payer_name = line[28:58].strip()
        amt_raw = line[58:].strip()
        cents = parse_v1_yuan_string(amt_raw, fallback_cents=0)
        if cents <= 0:
            continue
        parsed.append({
            "line_no": idx + 1,
            "tx_date": tx_date,
            "serial_no": serial_no,
            "payer_name": payer_name,
            "amount_cents": cents,
        })
    return parsed
