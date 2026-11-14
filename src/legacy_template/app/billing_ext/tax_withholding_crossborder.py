# -*- coding: utf-8 -*-
"""跨境 SaaS 预提所得税 (WHT - Withholding Tax) 双边税收协定税率表与税款倒算（Gross-Up）计算器。"""
from typing import Any, Dict

BILATERAL_WHT_TREATY_RATES_BPS: Dict[str, Dict[str, Any]] = {
    "SG": {"country": "Singapore", "standard_wht_bps": 1000, "treaty_royalty_wht_bps": 600, "gst_reverse_charge": True},
    "HK": {"country": "Hong Kong SAR", "standard_wht_bps": 1000, "treaty_royalty_wht_bps": 500, "gst_reverse_charge": False},
    "JP": {"country": "Japan", "standard_wht_bps": 2000, "treaty_royalty_wht_bps": 1000, "gst_reverse_charge": True},
    "DE": {"country": "Germany", "standard_wht_bps": 1500, "treaty_royalty_wht_bps": 1000, "gst_reverse_charge": True},
    "US": {"country": "United States", "standard_wht_bps": 3000, "treaty_royalty_wht_bps": 1000, "gst_reverse_charge": False},
}


def calculate_crossborder_wht_settlement(
    invoice_net_cents: int,
    jurisdiction_code: str,
    has_tax_residency_cert: bool = True,
    contract_gross_up_clause: bool = False,
) -> Dict[str, Any]:
    """计算境外客户代扣代缴预提所得税后实际到账净额，或含税包干条款下的 Gross-Up 合同总额。"""
    spec = BILATERAL_WHT_TREATY_RATES_BPS.get((jurisdiction_code or "SG").upper(), BILATERAL_WHT_TREATY_RATES_BPS["SG"])
    wht_bps = int(spec["treaty_royalty_wht_bps"] if has_tax_residency_cert else spec["standard_wht_bps"])
    amt = max(0, int(invoice_net_cents))

    if not contract_gross_up_clause:
        withheld = (amt * wht_bps) // 10000
        cash_remitted = amt - withheld
        billed_gross = amt
    else:
        # 净到手条款：Gross = Net / (1 - wht_rate)
        denom = max(1, 10000 - wht_bps)
        billed_gross = int(round((amt * 10000.0) / denom))
        withheld = billed_gross - amt
        cash_remitted = amt

    return {
        "jurisdiction": jurisdiction_code.upper(),
        "applied_wht_bps": wht_bps,
        "treaty_applied": has_tax_residency_cert,
        "gross_up_clause": contract_gross_up_clause,
        "billed_gross_cents": billed_gross,
        "wht_withheld_cents": withheld,
        "net_cash_remitted_cents": cash_remitted,
        "buyer_gst_reverse_charge_applicable": bool(spec["gst_reverse_charge"]),
    }
