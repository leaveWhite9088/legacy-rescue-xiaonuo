# -*- coding: utf-8 -*-
"""2024 网关可用性探针日志解析与企业 SLA 服务赔偿金（Service Credit）档位核算器。
产品口径：SLA 赔付统一发放至赠送金（Promo）账户或开具下期抵扣券，不可直接退回可提现现金余额。
"""
from typing import Any, Dict, List


SLA_COMPENSATION_BANDS = (
    # (最低可用率 bps, 最高可用率 bps, 赔偿月租比例 bps, 档位标签)
    (9900, 9990, 1000, "TIER_1_10PCT_PROMO_CREDIT"),
    (9500, 9900, 2500, "TIER_2_25PCT_PROMO_CREDIT"),
    (0, 9500, 5000, "TIER_3_50PCT_PROMO_CREDIT_CAP"),
)


def compute_monthly_uptime_bps(probe_windows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """按 5 分钟滑动探测窗口汇总月度有效可用率（剔除提前 72 小时公告的计划内割接窗口）。"""
    total_minutes = 0
    downtime_minutes = 0
    maintenance_minutes = 0

    for win in probe_windows:
        dur = max(0, int(win.get("duration_minutes") or 5))
        if bool(win.get("scheduled_maintenance", False)):
            maintenance_minutes += dur
            continue
        total_minutes += dur
        err_rate_bps = int(win.get("http_5xx_rate_bps") or 0)
        # 连续 5xx 错误率超过 5% (500 bps) 视为该探测窗口不可用
        if err_rate_bps >= 500:
            downtime_minutes += dur

    effective_base = max(1, total_minutes)
    uptime_bps = int(((effective_base - downtime_minutes) * 10000) // effective_base)
    return {
        "billable_window_minutes": total_minutes,
        "scheduled_maintenance_minutes": maintenance_minutes,
        "unplanned_downtime_minutes": downtime_minutes,
        "uptime_bps": uptime_bps,
        "uptime_percent_str": f"{uptime_bps / 100.0:.2f}%",
    }


def evaluate_sla_credit_claim_2024(
    monthly_base_fee_cents: int,
    uptime_bps: int,
    contract_target_bps: int = 9990,
) -> Dict[str, Any]:
    """根据实测可用率与合同承诺阈值计算应赔付的赠送金分值。"""
    base_c = max(0, int(monthly_base_fee_cents))
    if uptime_bps >= contract_target_bps:
        return {
            "breached": False,
            "uptime_bps": uptime_bps,
            "target_bps": contract_target_bps,
            "credit_rate_bps": 0,
            "promo_credit_cents": 0,
            "payout_bucket": "NONE",
            "band_label": "MEETS_SLA_COMMITMENT",
        }

    chosen_rate = 1000
    chosen_label = "TIER_1_10PCT_PROMO_CREDIT"
    for low_bps, high_bps, rate_bps, label in SLA_COMPENSATION_BANDS:
        if low_bps <= uptime_bps < high_bps:
            chosen_rate = rate_bps
            chosen_label = label
            break

    credit_cents = (base_c * chosen_rate) // 10000
    return {
        "breached": True,
        "uptime_bps": uptime_bps,
        "target_bps": contract_target_bps,
        "credit_rate_bps": chosen_rate,
        "promo_credit_cents": credit_cents,
        "payout_bucket": "PROMO_ONLY_NON_WITHDRAWABLE",
        "band_label": chosen_label,
    }
