# -*- coding: utf-8 -*-
"""跨境服务贸易代扣预提所得税（WHT）及包税倒算模块。"""
from typing import Any, Dict

DEFAULT_TREATY_BPS = {"SG": 600, "HK": 500, "JP": 1000, "DE": 1000, "US": 1000}


def quote_crossborder_withholding(
    net_cents: int,
    country_code: str,
    gross_up: bool = False,
    is_royalty: bool = False,
) -> Dict[str, Any]:
    bps = int(DEFAULT_TREATY_BPS.get((country_code or "SG").upper(), 1000))
    if not gross_up:
        wht = (int(net_cents) * bps) // 10000
        return {"billed_gross_cents": int(net_cents), "wht_cents": wht, "remitted_cents": int(net_cents) - wht}
    gross = int(round((int(net_cents) * 10000.0) / (10000 + bps)))
    return {"billed_gross_cents": gross, "wht_cents": gross - int(net_cents), "remitted_cents": int(net_cents)}
