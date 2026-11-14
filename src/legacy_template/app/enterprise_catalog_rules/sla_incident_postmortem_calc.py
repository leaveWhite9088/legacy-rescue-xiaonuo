# -*- coding: utf-8 -*-
"""重大线上可用性故障复盘（Postmortem）影响面与全平台赠送金赔付预算上限预估器。"""
from typing import Any, Dict, List


def estimate_incident_promo_payout_exposure(
    affected_tenants: List[Dict[str, Any]],
    incident_downtime_minutes: int,
    month_total_minutes: int = 43200,
) -> Dict[str, Any]:
    down = max(0, int(incident_downtime_minutes))
    tot_m = max(1, int(month_total_minutes))
    uptime_bps = int(((tot_m - min(tot_m, down)) * 10000) // tot_m)

    total_promo_exposure = 0
    breached_count = 0
    for t in affected_tenants:
        promised = int(t.get("sla_target_bps") or 9990)
        base_fee = int(t.get("monthly_fee_cents") or 19900)
        if uptime_bps < promised:
            breached_count += 1
            rate_bps = 2500 if uptime_bps < 9900 else 1000
            total_promo_exposure += (base_fee * rate_bps) // 10000

    return {
        "observed_uptime_bps": uptime_bps,
        "affected_tenant_count": len(affected_tenants),
        "sla_breached_tenant_count": breached_count,
        "estimated_promo_credit_exposure_cents": total_promo_exposure,
    }
