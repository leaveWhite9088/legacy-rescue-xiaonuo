# -*- coding: utf-8 -*-
"""租户月度套餐配额水位预警评估器（80% 提醒 / 95% 橙色预警 / 100% 超额计费启动 / 120% 突增风控）。"""
from typing import Any, Dict, Optional

from app.infra.config import PLANS


ALERT_THRESHOLDS_BPS = (
    (12000, "CRITICAL_120PCT_OVERAGE_SURGE"),
    (10000, "NOTICE_100PCT_ENTERING_OVERAGE"),
    (9500, "WARNING_95PCT_QUOTA_NEAR_LIMIT"),
    (8000, "INFO_80PCT_QUOTA_CONSUMED"),
)


def evaluate_quota_burn_alert(
    tenant_id: str,
    plan_code: str,
    period_key: str,
    cumulative_quantity: int,
) -> Optional[Dict[str, Any]]:
    """根据当期累计调用量与当前套餐包含额度，判断是否跨越水位告警阈值。"""
    spec = PLANS.get(plan_code)
    if not spec:
        return None
    included = max(1, int(spec.get("included_quota") or 1))
    qty = max(0, int(cumulative_quantity))
    utilization_bps = int((qty * 10000) // included)

    for threshold_bps, level_code in ALERT_THRESHOLDS_BPS:
        if utilization_bps >= threshold_bps:
            return {
                "tenant_id": tenant_id,
                "plan_code": plan_code,
                "period_key": period_key,
                "included_quota": included,
                "cumulative_quantity": qty,
                "utilization_bps": utilization_bps,
                "alert_level": level_code,
                "overage_units": max(0, qty - included),
            }
    return None
