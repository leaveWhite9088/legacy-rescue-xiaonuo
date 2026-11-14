# -*- coding: utf-8 -*-
"""东南亚及跨境技术服务费预提所得税（Withholding Tax, WHT）双边税收协定抵免计算器。"""
from typing import Any, Dict


TREATY_WHT_RATES_BPS = {
    "SG": 600,    # 中新协定特许权/技术费优惠税率 6%
    "HK": 500,    # 内地与香港安排 5%
    "MY": 1000,   # 马来西亚 10%
    "ID": 1000,   # 印尼 10%
    "DEFAULT_NON_TREATY": 1000,
}


def calculate_cross_border_wht(
    invoice_net_cents: int,
    country_iso2: str,
    has_tax_residency_cert: bool = True,
    gross_up_clause: bool = False,
) -> Dict[str, Any]:
    code = (country_iso2 or "").strip().upper()
    rate_bps = TREATY_WHT_RATES_BPS.get(code, 1000) if has_tax_residency_cert else 1500
    net = max(0, int(invoice_net_cents))

    if gross_up_clause and rate_bps < 10000:
        grossed_up = (net * 10000 + (10000 - rate_bps) // 2) // (10000 - rate_bps)
        wht_cents = grossed_up - net
        remit_to_vendor = net
        total_buyer_cost = grossed_up
    else:
        wht_cents = (net * rate_bps + 5000) // 10000
        remit_to_vendor = net - wht_cents
        total_buyer_cost = net

    return {
        "country": code or "UNKNOWN",
        "applied_wht_rate_bps": rate_bps,
        "wht_tax_cents": wht_cents,
        "remit_to_supplier_cents": remit_to_vendor,
        "buyer_total_cash_outflow_cents": total_buyer_cost,
    }
