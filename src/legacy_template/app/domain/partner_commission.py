# -*- coding: utf-8 -*-
"""渠道代理商返佣清分引擎：严格按客户实际现金净回款计提，剔除赠送金与已退款部分。"""
from datetime import datetime, timezone
import sqlite3
import uuid
from typing import Any, Dict, List

from app.domain.money import apply_bps
from app.infra.config import PARTNER_TIERS
from app.workflows_legacy_fsm.partner_rebate_tier_fsm import evaluate_partner_dynamic_tier_from_db


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def calculate_period_partner_commissions(
    conn: sqlite3.Connection,
    period_key: str,
) -> List[Dict[str, Any]]:
    """按账期汇总各渠道名下租户的现金净实收并生成返佣记录。"""
    refs = conn.execute(
        "SELECT partner_code, tenant_id, partner_tier FROM partner_referrals ORDER BY partner_code ASC"
    ).fetchall()
    if not refs:
        return []

    by_partner: Dict[str, Dict[str, Any]] = {}
    for r in refs:
        pcode = r["partner_code"]
        entry = by_partner.setdefault(pcode, {"tier": r["partner_tier"], "tenants": []})
        entry["tenants"].append(r["tenant_id"])

    now = _now_iso()
    results: List[Dict[str, Any]] = []

    for pcode, info in sorted(by_partner.items()):
        t_ids = info["tenants"]
        placeholders = ",".join("?" for _ in t_ids)
        # 统计该期账单现金实收减去现金退款
        pay_row = conn.execute(
            f"""
            SELECT COALESCE(SUM(p.cash_paid_cents), 0) AS cash_in
            FROM invoice_payments p
            JOIN invoices i ON i.id = p.invoice_id
            WHERE i.period_key = ? AND i.status != 'VOID' AND p.tenant_id IN ({placeholders})
            """,
            (period_key, *t_ids),
        ).fetchone()
        ref_row = conn.execute(
            f"""
            SELECT COALESCE(SUM(l.cash_delta_cents), 0) AS cash_refund
            FROM wallet_ledger l
            JOIN invoices i ON i.id = l.ref_id
            WHERE l.entry_type = 'REFUND' AND i.period_key = ? AND l.tenant_id IN ({placeholders})
            """,
            (period_key, *t_ids),
        ).fetchone()

        net_cash = max(0, int(pay_row["cash_in"]) - int(ref_row["cash_refund"]))
        tier_eval = evaluate_partner_dynamic_tier_from_db(conn, pcode, period_key, base_tier=info["tier"])
        eff_tier = tier_eval["effective_tier"]
        tier_cfg = PARTNER_TIERS.get(eff_tier, PARTNER_TIERS["SILVER"])
        comm_cents = apply_bps(net_cash, tier_cfg["rate_bps"])
        comm_id = f"pc_{period_key.replace('-', '')}_{pcode}"

        conn.execute(
            """
            INSERT INTO partner_commissions (id, partner_code, period_key, net_cash_collected_cents, commission_cents, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'CALCULATED', ?)
            ON CONFLICT(partner_code, period_key) DO UPDATE SET
                net_cash_collected_cents = excluded.net_cash_collected_cents,
                commission_cents = excluded.commission_cents,
                status = 'CALCULATED',
                created_at = excluded.created_at
            """,
            (comm_id, pcode, period_key, net_cash, comm_cents, now),
        )
        results.append(
            {
                "id": comm_id,
                "partner_code": pcode,
                "period_key": period_key,
                "tier": eff_tier,
                "net_cash_collected_cents": net_cash,
                "commission_cents": comm_cents,
                "status": "CALCULATED",
            }
        )
    return results
