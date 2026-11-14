# -*- coding: utf-8 -*-
"""多要素捆绑销售单独售价（SSP - Standalone Selling Price）四分位走廊（±15% Narrow Band）合规偏离度检验器。"""
from typing import Any, Dict, List


def calibrate_historical_ssp_corridor(
    sku_code: str,
    historical_standalone_prices_cents: List[int],
    band_half_width_bps: int = 1500,
) -> Dict[str, Any]:
    cleaned = sorted(int(x) for x in historical_standalone_prices_cents if int(x) > 0)
    if not cleaned:
        return {"sku_code": sku_code, "established_ssp": False, "median_cents": 0}

    n = len(cleaned)
    mid = n // 2
    median_c = cleaned[mid] if n % 2 == 1 else (cleaned[mid - 1] + cleaned[mid]) // 2
    lo_bound = median_c - (median_c * band_half_width_bps) // 10000
    hi_bound = median_c + (median_c * band_half_width_bps) // 10000

    in_band_cnt = sum(1 for x in cleaned if lo_bound <= x <= hi_bound)
    concentration_bps = int((in_band_cnt * 10000) // n)
    # 实务中若 >= 75% 的独立历史成交落在中位数 ±15% 走廊内，即认定具备可观察单独售价
    return {
        "sku_code": sku_code,
        "sample_count": n,
        "median_cents": median_c,
        "corridor_low_cents": lo_bound,
        "corridor_high_cents": hi_bound,
        "in_corridor_concentration_bps": concentration_bps,
        "established_ssp": concentration_bps >= 7500,
    }
