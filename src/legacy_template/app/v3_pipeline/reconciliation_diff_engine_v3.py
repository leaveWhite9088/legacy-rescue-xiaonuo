# -*- coding: utf-8 -*-
"""v3 三方资金对账图比对引擎原型（比对渠道回单、钱包流水与发票支付明细三者孤儿记录）。"""
from typing import Any, Dict, Iterable, List


def run_three_way_payment_graph_diff(
    channel_receipts: Iterable[Dict[str, Any]],
    ledger_entries: Iterable[Dict[str, Any]],
    invoice_payments: Iterable[Dict[str, Any]],
) -> Dict[str, Any]:
    ch_by_ref = {str(r["ref_id"]): int(r["amount_cents"]) for r in channel_receipts if r.get("ref_id")}
    led_by_ref: Dict[str, int] = {}
    for l in ledger_entries:
        ref = str(l.get("ref_id") or "")
        if not ref:
            continue
        amt = abs(int(l.get("cash_delta_cents") or 0)) + abs(int(l.get("promo_delta_cents") or 0))
        led_by_ref[ref] = led_by_ref.get(ref, 0) + amt

    pay_by_inv: Dict[str, int] = {}
    for p in invoice_payments:
        iid = str(p.get("invoice_id") or "")
        if not iid:
            continue
        pay_by_inv[iid] = pay_by_inv.get(iid, 0) + int(p.get("total_paid_cents") or 0)

    all_refs = sorted(set(ch_by_ref.keys()) | set(led_by_ref.keys()) | set(pay_by_inv.keys()))
    discrepancies: List[Dict[str, Any]] = []

    for ref in all_refs:
        in_ch = ch_by_ref.get(ref)
        in_led = led_by_ref.get(ref)
        in_pay = pay_by_inv.get(ref)
        present_vals = [v for v in (in_ch, in_led, in_pay) if v is not None]
        if len(set(present_vals)) > 1 or (in_pay is not None and in_led is None):
            discrepancies.append({
                "ref_id": ref,
                "channel_cents": in_ch,
                "ledger_cents": in_led,
                "invoice_payment_cents": in_pay,
            })

    return {
        "correlated_keys": len(all_refs),
        "discrepancy_count": len(discrepancies),
        "discrepancies": discrepancies,
    }
