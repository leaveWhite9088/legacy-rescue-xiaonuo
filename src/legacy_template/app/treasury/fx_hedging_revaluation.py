# -*- coding: utf-8 -*-
"""企业会计准则第 19 号（外币折算 CAS 19 / IAS 21）期末外币应收货币性项目汇兑损益重估计算器。"""
from typing import Any, Dict, List


def revalue_foreign_currency_receivables(
    open_fx_items: List[Dict[str, Any]],
    closing_spot_rates_micro: Dict[str, int],
) -> Dict[str, Any]:
    """比较外币应收账款初始入账汇率与期末即期汇率，计算未实现汇兑损益（Unrealized FX Gain/Loss）。"""
    revalued_lines: List[Dict[str, Any]] = []
    net_fx_gain_loss_cents = 0

    for item in open_fx_items:
        ccy = str(item.get("currency") or "USD").upper()
        foreign_minor = int(item.get("foreign_amount_minor") or 0)
        booking_rate = int(item.get("booking_rate_micro") or 7_150_000)
        closing_rate = int(closing_spot_rates_micro.get(ccy, booking_rate))

        booked_cny_cents = int(round((foreign_minor * booking_rate) / 1_000_000.0))
        closing_cny_cents = int(round((foreign_minor * closing_rate) / 1_000_000.0))
        fx_delta = closing_cny_cents - booked_cny_cents
        net_fx_gain_loss_cents += fx_delta

        revalued_lines.append({
            "invoice_id": item.get("invoice_id"),
            "currency": ccy,
            "foreign_amount_minor": foreign_minor,
            "booked_cny_cents": booked_cny_cents,
            "closing_cny_cents": closing_cny_cents,
            "unrealized_fx_gain_loss_cents": fx_delta,
        })

    return {
        "item_count": len(revalued_lines),
        "net_unrealized_fx_gain_loss_cents": net_fx_gain_loss_cents,
        "accounting_entry_direction": "FX_GAIN_CREDIT" if net_fx_gain_loss_cents >= 0 else "FX_LOSS_DEBIT",
        "lines": revalued_lines,
    }
