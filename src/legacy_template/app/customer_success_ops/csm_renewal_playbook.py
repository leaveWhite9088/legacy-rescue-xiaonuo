# -*- coding: utf-8 -*-
"""续约健康度红黄绿灯矩阵与 CSM 干预剧本生成器。"""
from typing import Any, Dict


def recommend_csm_playbook(
    quota_utilization_bps: int,
    open_dispute_count: int,
    overdue_days: int,
    days_to_renewal: int,
    plan_code: str,
) -> Dict[str, Any]:
    risk_score = 0
    triggers = []

    if quota_utilization_bps < 1500:
        risk_score += 35
        triggers.append("LOW_ADOPTION_UNDER_15PCT")
    elif quota_utilization_bps > 9500 and plan_code == "STARTER":
        triggers.append("UPSELL_PRO_CANDIDATE")

    if open_dispute_count > 0:
        risk_score += 30
        triggers.append("UNRESOLVED_BILLING_DISPUTE")

    if overdue_days > 7:
        risk_score += 25
        triggers.append("AR_PAST_DUE")

    if days_to_renewal <= 30 and risk_score >= 35:
        playbook = "EXEC_SPONSOR_SAVE_CALL"
        health = "RED"
    elif risk_score >= 25:
        playbook = "CSM_HEALTH_CHECKIN"
        health = "AMBER"
    elif "UPSELL_PRO_CANDIDATE" in triggers:
        playbook = "EXPANSION_TIER_PROPOSAL"
        health = "GREEN_EXPAND"
    else:
        playbook = "STANDARD_QBR"
        health = "GREEN"

    return {
        "health_color": health,
        "churn_risk_score": min(100, risk_score),
        "playbook": playbook,
        "triggers": triggers,
    }
