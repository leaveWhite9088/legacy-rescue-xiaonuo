# -*- coding: utf-8 -*-
"""企业年框客户年度最低用量承诺差额补齐（Annual Minimum Take-or-Pay True-Up）与季度配额结转（Rollover）试算器。"""
from typing import Any, Dict, List


def simulate_annual_take_or_pay_trueup(
    annual_committed_cents: int,
    monthly_actual_spend_cents: List[int],
    allow_shortfall_grace_bps: int = 0,
) -> Dict[str, Any]:
    """核算 12 个月累计税前有效消费是否达到年框保底承诺额，计算年末第 12 期应补齐差额（True-Up Charge）。"""
    commit = max(0, int(annual_committed_cents))
    clean_months = [max(0, int(x)) for x in (monthly_actual_spend_cents or [])]
    actual_cum = sum(clean_months)

    effective_floor = commit - (commit * max(0, min(2000, int(allow_shortfall_grace_bps)))) // 10000
    shortfall_cents = max(0, effective_floor - actual_cum)
    attainment_bps = int((actual_cum * 10000) // max(1, commit))

    return {
        "months_recorded": len(clean_months),
        "annual_committed_cents": commit,
        "effective_floor_after_grace_cents": effective_floor,
        "cumulative_actual_spend_cents": actual_cum,
        "attainment_bps": attainment_bps,
        "year_end_trueup_charge_cents": shortfall_cents,
        "commitment_satisfied": shortfall_cents == 0,
    }


def simulate_quarterly_quota_rollover(
    monthly_included_quota: int,
    quarter_monthly_usages: List[int],
    max_rollover_ratio_bps: int = 3000,
) -> Dict[str, Any]:
    """模拟增值包特性：上月未用完的内含配额最多按 30% 结转至下月（次月优先消耗当月配额，结转配额季末清零）。"""
    inc = max(0, int(monthly_included_quota))
    cap_rollover = (inc * max(0, min(10000, int(max_rollover_ratio_bps)))) // 10000
    carried_in = 0
    ledger: List[Dict[str, int]] = []

    for idx, raw_u in enumerate(quarter_monthly_usages[:3], start=1):
        used = max(0, int(raw_u))
        used_from_base = min(inc, used)
        rem_need = used - used_from_base
        used_from_rollover = min(carried_in, rem_need)
        billable_overage = rem_need - used_from_rollover

        unused_base = inc - used_from_base
        carried_out = min(cap_rollover, unused_base) if idx < 3 else 0
        ledger.append({
            "month_in_quarter": idx,
            "raw_usage": used,
            "rollover_in": carried_in,
            "consumed_base": used_from_base,
            "consumed_rollover": used_from_rollover,
            "billable_overage_units": billable_overage,
            "rollover_out": carried_out,
        })
        carried_in = carried_out

    return {
        "monthly_included_quota": inc,
        "rollover_cap_units": cap_rollover,
        "quarter_total_billable_overage": sum(x["billable_overage_units"] for x in ledger),
        "months": ledger,
    }
