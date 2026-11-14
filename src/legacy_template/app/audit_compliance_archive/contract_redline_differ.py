# -*- coding: utf-8 -*-
"""大客户框架合同补充协议（Amendment）条款变更风险评分器。"""
from typing import Any, Dict, List


def score_contract_amendment_risk(old_terms: Dict[str, Any], new_terms: Dict[str, Any]) -> Dict[str, Any]:
    flags: List[str] = []
    risk_points = 0

    old_commit = int(old_terms.get("min_monthly_commit_cents") or 0)
    new_commit = int(new_terms.get("min_monthly_commit_cents") or 0)
    if new_commit < old_commit:
        flags.append("COMMITMENT_DOWNSIZE")
        risk_points += 35

    old_disc = int(old_terms.get("custom_overage_discount_bps") or 0)
    new_disc = int(new_terms.get("custom_overage_discount_bps") or 0)
    if new_disc > old_disc + 500:
        flags.append("DEEP_DISCOUNT_EXPANSION")
        risk_points += 25
    if new_disc > 2500:
        flags.append("EXCEEDS_VP_SALES_DELEGATION_CAP")
        risk_points += 40

    old_credit = int(old_terms.get("credit_limit_cents") or 0)
    new_credit = int(new_terms.get("credit_limit_cents") or 0)
    if new_credit > old_credit * 2 and new_credit > 500_000:
        flags.append("CREDIT_EXPOSURE_DOUBLED")
        risk_points += 20

    tier = "CFO_SIGN_REQUIRED" if risk_points >= 50 else ("FINANCE_DIRECTOR_REVIEW" if risk_points >= 25 else "AUTO_APPROVED")
    return {
        "risk_score": risk_points,
        "approval_tier": tier,
        "risk_flags": flags,
    }
