# -*- coding: utf-8 -*-
"""多年期企业框架合同年度 CPI 物价指数调价条款（Escalation Clause）核算器。"""
from typing import Any, Dict, List


DEFAULT_CPI_CAP_BPS = 500     # 年度上浮封顶 5.00%
DEFAULT_CPI_FLOOR_BPS = 150   # 年度保底上浮 1.50%


def project_multi_year_contract_fees(
    year1_monthly_cents: int,
    contract_years: int,
    published_cpi_bps_by_year: List[int],
    cap_bps: int = DEFAULT_CPI_CAP_BPS,
    floor_bps: int = DEFAULT_CPI_FLOOR_BPS,
    waive_year2_escalation: bool = False,
) -> Dict[str, Any]:
    years = max(1, min(int(contract_years), 10))
    cur_monthly = max(0, int(year1_monthly_cents))
    schedule = []
    total_tcv_cents = 0

    for yr in range(1, years + 1):
        if yr == 1:
            applied_bps = 0
        elif yr == 2 and waive_year2_escalation:
            applied_bps = 0
        else:
            idx = min(yr - 2, len(published_cpi_bps_by_year) - 1) if published_cpi_bps_by_year else 0
            raw_cpi = int(published_cpi_bps_by_year[idx]) if published_cpi_bps_by_year else floor_bps
            applied_bps = max(int(floor_bps), min(int(cap_bps), raw_cpi))
            cur_monthly = (cur_monthly * (10000 + applied_bps) + 5000) // 10000

        acv = cur_monthly * 12
        total_tcv_cents += acv
        schedule.append(
            {
                "contract_year": yr,
                "applied_escalation_bps": applied_bps,
                "monthly_fee_cents": cur_monthly,
                "annual_acv_cents": acv,
            }
        )

    return {
        "contract_years": years,
        "total_tcv_cents": total_tcv_cents,
        "average_acv_cents": total_tcv_cents // years,
        "schedule": schedule,
    }
