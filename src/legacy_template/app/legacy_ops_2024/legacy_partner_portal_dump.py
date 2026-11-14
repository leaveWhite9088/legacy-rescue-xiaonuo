# -*- coding: utf-8 -*-
"""2024 渠道代理商季度返佣对账单与争议冻结扣回（Clawback）批处理导出工具。"""
import sqlite3
from typing import Any, Dict, List


PARTNER_REBATE_MATRIX_2024: Dict[str, Dict[str, int]] = {
    "SILVER": {"base_rebate_bps": 800, "quarterly_target_cents": 500_000, "accelerator_bps": 200},
    "GOLD": {"base_rebate_bps": 1200, "quarterly_target_cents": 1_500_000, "accelerator_bps": 300},
    "PLATINUM": {"base_rebate_bps": 1800, "quarterly_target_cents": 4_000_000, "accelerator_bps": 400},
}


def generate_partner_quarterly_settlement_dump(
    conn: sqlite3.Connection,
    period_keys: List[str],
) -> List[Dict[str, Any]]:
    """汇总指定账期集合内各渠道代理商名下租户的实收净额、争议挂起金额与应发返佣。"""
    partners = conn.execute("SELECT * FROM partner_referrals ORDER BY partner_code ASC").fetchall()
    by_partner: Dict[str, Dict[str, Any]] = {}

    for row in partners:
        p_code = row["partner_code"]
        tier = (row["partner_tier"] or "SILVER").upper()
        spec = PARTNER_REBATE_MATRIX_2024.get(tier, PARTNER_REBATE_MATRIX_2024["SILVER"])
        bucket = by_partner.setdefault(
            p_code,
            {
                "partner_code": p_code,
                "partner_tier": tier,
                "referred_tenants": [],
                "eligible_cash_collected_cents": 0,
                "disputed_holdback_cents": 0,
                "void_clawback_cents": 0,
                "spec": spec,
            },
        )
        tid = row["tenant_id"]
        bucket["referred_tenants"].append(tid)

        if not period_keys:
            continue
        placeholders = ",".join("?" for _ in period_keys)
        invs = conn.execute(
            f"SELECT id, status, total_cents, paid_cents, refunded_cents FROM invoices WHERE tenant_id = ? AND period_key IN ({placeholders})",
            [tid, *period_keys],
        ).fetchall()

        for inv in invs:
            st = inv["status"]
            tot = int(inv["total_cents"] or 0)
            paid = int(inv["paid_cents"] or 0)
            ref = int(inv["refunded_cents"] or 0)
            if st == "PAID":
                # 仅现金实付部分参与渠道返佣，赠送金抵扣部分不计返佣基数
                pay_row = conn.execute(
                    "SELECT COALESCE(SUM(cash_paid_cents), 0) AS c_paid FROM invoice_payments WHERE invoice_id = ?",
                    (inv["id"],),
                ).fetchone()
                c_paid = int(pay_row["c_paid"] or 0) if pay_row else paid
                net_cash = max(0, c_paid - ref)
                bucket["eligible_cash_collected_cents"] += net_cash
            elif st == "DISPUTED":
                bucket["disputed_holdback_cents"] += tot
            elif st == "VOID":
                bucket["void_clawback_cents"] += tot

    output: List[Dict[str, Any]] = []
    for p_code, data in sorted(by_partner.items()):
        spec = data.pop("spec")
        eligible = data["eligible_cash_collected_cents"]
        rate_bps = spec["base_rebate_bps"]
        if eligible >= spec["quarterly_target_cents"]:
            rate_bps += spec["accelerator_bps"]
        gross_commission = (eligible * rate_bps) // 10000
        holdback_reserve = (data["disputed_holdback_cents"] * spec["base_rebate_bps"]) // 10000
        payable = max(0, gross_commission - holdback_reserve)
        data.update(
            {
                "applied_rebate_bps": rate_bps,
                "gross_commission_cents": gross_commission,
                "dispute_holdback_reserve_cents": holdback_reserve,
                "net_payable_commission_cents": payable,
            }
        )
        output.append(data)
    return output
