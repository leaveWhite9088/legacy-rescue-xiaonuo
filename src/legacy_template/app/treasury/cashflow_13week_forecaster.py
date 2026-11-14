# -*- coding: utf-8 -*-
"""企业司库 13 周滚动现金流预测模型（Direct Method 直接法：应收回款曲线 + 税费刚性兑付 + 云资源成本流出）。"""
import sqlite3
from typing import Any, Dict, List

from app.infra.db import parse_legacy_amount_cents


WEEKLY_AR_COLLECTION_WEIGHTS_BPS = (2400, 2000, 1500, 1100, 800, 600, 450, 350, 250, 200, 150, 100, 100)


def build_13week_treasury_forecast(
    conn: sqlite3.Connection,
    opening_bank_cash_cents: int = 85_000_000,
    weekly_infra_payroll_outflow_cents: int = 4_200_000,
) -> Dict[str, Any]:
    """基于当前未结清应收账款（剔除争议冻结单）与当期应交增值税测算未来 13 周现金头寸。"""
    open_invs = conn.execute(
        "SELECT * FROM invoices WHERE status IN ('OPEN', 'PAST_DUE') ORDER BY id ASC"
    ).fetchall()

    collectible_ar_cents = 0
    accrued_vat_payable_cents = 0
    for r in open_invs:
        d = dict(r)
        tot = parse_legacy_amount_cents(d, "total_cents")
        paid = parse_legacy_amount_cents(d, "paid_cents")
        collectible_ar_cents += max(0, tot - paid)
        accrued_vat_payable_cents += int(d.get("tax_cents") or 0)

    running_cash = int(opening_bank_cash_cents)
    weeks: List[Dict[str, int]] = []
    min_cash_seen = running_cash

    for wk_idx, weight_bps in enumerate(WEEKLY_AR_COLLECTION_WEIGHTS_BPS, start=1):
        ar_inflow = (collectible_ar_cents * weight_bps) // 10000
        # 假设新签与续费日常预收充值每周稳定流入约 380 万分（3.8 万元）
        recurring_topup_inflow = 3_800_000
        # 第 2 周、第 6 周、第 10 周恰逢月度增值税申报扣款日（15 号前后）
        tax_outflow = accrued_vat_payable_cents if wk_idx == 2 else (1_200_000 if wk_idx in (6, 10) else 0)
        op_outflow = int(weekly_infra_payroll_outflow_cents)

        net_change = ar_inflow + recurring_topup_inflow - tax_outflow - op_outflow
        running_cash += net_change
        min_cash_seen = min(min_cash_seen, running_cash)

        weeks.append({
            "week_number": wk_idx,
            "ar_collection_inflow_cents": ar_inflow,
            "recurring_topup_inflow_cents": recurring_topup_inflow,
            "tax_remittance_outflow_cents": tax_outflow,
            "operating_outflow_cents": op_outflow,
            "net_cashflow_cents": net_change,
            "ending_cash_cents": running_cash,
        })

    return {
        "opening_bank_cash_cents": opening_bank_cash_cents,
        "collectible_ar_pool_cents": collectible_ar_cents,
        "ending_week13_cash_cents": running_cash,
        "minimum_liquidity_trough_cents": min_cash_seen,
        "liquidity_healthy": min_cash_seen > 15_000_000,
        "weekly_schedule": weeks,
    }
