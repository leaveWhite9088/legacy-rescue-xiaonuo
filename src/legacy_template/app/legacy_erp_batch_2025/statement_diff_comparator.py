# -*- coding: utf-8 -*-
"""客户自有采购台账（Customer AP Ledger）与云策应收账单（YunCe AR Ledger）逐单差异分类比对引擎。
支持自动识别：时间性未达差异（Timing Difference）、价外税率口径理解差异（Tax Basis Difference）、
历史封账跨期红冲未并表差异（Prior-Period Adjustment Unmerged）及真实金额偏差。
"""
from typing import Any, Dict, List


def compare_customer_ap_vs_platform_ar(
    customer_ap_rows: List[Dict[str, Any]],
    platform_ar_rows: List[Dict[str, Any]],
    platform_adjustments: List[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    ap_by_inv = {str(r.get("invoice_id") or ""): r for r in customer_ap_rows if r.get("invoice_id")}
    ar_by_inv = {str(r.get("id") or r.get("invoice_id") or ""): r for r in platform_ar_rows if (r.get("id") or r.get("invoice_id"))}

    adj_by_ref: Dict[str, int] = {}
    for adj in (platform_adjustments or []):
        ref = str(adj.get("ref_invoice_id") or "")
        if ref:
            adj_by_ref[ref] = adj_by_ref.get(ref, 0) + int(adj.get("delta_cents") or 0)

    all_ids = sorted(set(ap_by_inv.keys()) | set(ar_by_inv.keys()))
    matched_count = 0
    variances: List[Dict[str, Any]] = []

    for inv_id in all_ids:
        ap = ap_by_inv.get(inv_id)
        ar = ar_by_inv.get(inv_id)
        if ap is None:
            variances.append({
                "invoice_id": inv_id,
                "category": "MISSING_IN_CUSTOMER_AP_TIMING_LAG",
                "platform_cents": int(ar.get("total_cents") or 0),
                "customer_cents": 0,
            })
            continue
        if ar is None:
            variances.append({
                "invoice_id": inv_id,
                "category": "UNRECOGNIZED_INVOICE_ID_IN_PLATFORM",
                "platform_cents": 0,
                "customer_cents": int(ap.get("recorded_cents") or 0),
            })
            continue

        p_gross = int(ar.get("total_cents") or 0)
        p_tax = int(ar.get("tax_cents") or 0)
        c_amt = int(ap.get("recorded_cents") or 0)
        net_after_adj = p_gross + adj_by_ref.get(inv_id, 0)

        if p_gross == c_amt:
            matched_count += 1
        elif net_after_adj == c_amt:
            variances.append({
                "invoice_id": inv_id,
                "category": "RECONCILED_AFTER_OPEN_PERIOD_BILLING_ADJUSTMENT",
                "platform_cents": p_gross,
                "adjustment_delta_cents": adj_by_ref.get(inv_id, 0),
                "customer_cents": c_amt,
            })
        elif p_tax > 0 and (p_gross - p_tax) == c_amt:
            variances.append({
                "invoice_id": inv_id,
                "category": "CUSTOMER_BOOKED_PRETAX_EXCLUDING_EXCLUSIVE_VAT",
                "platform_cents": p_gross,
                "customer_cents": c_amt,
                "tax_cents": p_tax,
            })
        else:
            variances.append({
                "invoice_id": inv_id,
                "category": "UNEXPLAINED_AMOUNT_DISCREPANCY",
                "platform_cents": p_gross,
                "customer_cents": c_amt,
                "diff_cents": p_gross - c_amt,
            })

    return {
        "compared_invoice_count": len(all_ids),
        "exact_match_count": matched_count,
        "variance_count": len(variances),
        "variances": variances,
    }
