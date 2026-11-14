# -*- coding: utf-8 -*-
"""直销团队（AE / SDR / CSM）月度回款提成核算、超额加速阶梯（Accelerators）与退款倒扣（Clawback）计算引擎。"""
from typing import Any, Dict, List


COMMISSION_ACCELERATOR_BANDS = (
    # (配额达成下限 bps, 配额达成上限 bps, 提成比例 bps)
    (0, 10000, 600),        # 0% ~ 100% 达成率：6.0% 基础提成
    (10000, 13000, 950),    # 100% ~ 130% 达成率：9.5% 一阶加速
    (13000, 999999, 1350),  # > 130% 达成率：13.5% 超额冲刺奖励
)


def compute_rep_monthly_commission(
    rep_id: str,
    monthly_quota_cents: int,
    collected_cash_invoices: List[Dict[str, Any]],
    refunded_or_voided_invoices: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """按实际现金回款净额计算销售代表当月应发提成（赠送金抵扣额与未实收挂账不计入业绩基数）。"""
    quota = max(1, int(monthly_quota_cents))
    gross_eligible_cents = 0
    for inv in collected_cash_invoices:
        # 严格剥离税额与赠送金支付部分，仅以不含税现金实收计提
        cash_paid = int(inv.get("cash_paid_cents") or 0)
        tax_cents = int(inv.get("tax_cents") or 0)
        net_eligible = max(0, cash_paid - tax_cents)
        gross_eligible_cents += net_eligible

    clawback_base_cents = 0
    for r_inv in refunded_or_voided_invoices:
        clawback_base_cents += max(0, int(r_inv.get("cash_refunded_cents") or 0))

    net_attainment_cents = max(0, gross_eligible_cents - clawback_base_cents)
    attainment_bps = int((net_attainment_cents * 10000) // quota)

    remaining = net_attainment_cents
    commission_cents = 0
    tier_breakdown: List[Dict[str, int]] = []

    for lo_bps, hi_bps, rate_bps in COMMISSION_ACCELERATOR_BANDS:
        band_lo_amt = (quota * lo_bps) // 10000
        band_hi_amt = (quota * hi_bps) // 10000
        if net_attainment_cents <= band_lo_amt:
            break
        taxable_in_band = min(net_attainment_cents, band_hi_amt) - band_lo_amt
        payout = (taxable_in_band * rate_bps) // 10000
        commission_cents += payout
        remaining -= taxable_in_band
        tier_breakdown.append({
            "band_low_bps": lo_bps,
            "band_high_bps": hi_bps,
            "rate_bps": rate_bps,
            "eligible_cents_in_band": taxable_in_band,
            "payout_cents": payout,
        })

    return {
        "rep_id": rep_id,
        "monthly_quota_cents": quota,
        "gross_cash_eligible_cents": gross_eligible_cents,
        "clawback_deduction_cents": clawback_base_cents,
        "net_attainment_cents": net_attainment_cents,
        "attainment_bps": attainment_bps,
        "total_commission_cents": commission_cents,
        "tier_breakdown": tier_breakdown,
    }
