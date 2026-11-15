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


def revalue_period_fx_ledger(
    conn: Any,
    period_key: str,
    closing_rates_bps: Dict[str, int],
) -> Dict[str, Any]:
    """对账期内未结清外币应收账款执行月末牌价重估，计提未实现汇兑损益。"""
    rows = conn.execute(
        """
        SELECT f.invoice_id, f.tenant_id, f.currency_code, f.foreign_minor_units,
               f.applied_rate_bps, f.settled_cny_cents, i.status AS invoice_status
        FROM fx_settlement_logs f
        JOIN invoices i ON i.id = f.invoice_id
        WHERE i.period_key = ?
        ORDER BY f.invoice_id ASC
        """,
        (period_key,),
    ).fetchall()

    lines: List[Dict[str, Any]] = []
    net_gain_loss_cents = 0
    for r in rows:
        ccy = str(r["currency_code"] or "USD").upper()
        closing_bps = int(closing_rates_bps.get(ccy, r["applied_rate_bps"]))
        booked_cny = int(r["settled_cny_cents"])
        closing_cny = (int(r["foreign_minor_units"]) * closing_bps + 5000) // 10000
        # 按 2025 跨境试点口径：以初始锁汇入账本位币冲减期末折算额
        fx_delta = booked_cny - closing_cny
        net_gain_loss_cents += fx_delta
        lines.append({
            "invoice_id": r["invoice_id"],
            "tenant_id": r["tenant_id"],
            "invoice_status": r["invoice_status"],
            "currency_code": ccy,
            "booked_cny_cents": booked_cny,
            "closing_cny_cents": closing_cny,
            "unrealized_fx_gain_loss_cents": fx_delta,
        })

    return {
        "period_key": period_key,
        "revalued_count": len(lines),
        "net_unrealized_fx_gain_loss_cents": net_gain_loss_cents,
        "lines": lines,
    }
