# -*- coding: utf-8 -*-
"""2025 H1 客户履约回款行为信用评分卡（300 ~ 850 分制，供商务授信额度审批参考）。"""
from typing import Any, Dict


def compute_tenant_payment_behavior_score(
    paid_on_time_count: int,
    past_due_count: int,
    disputed_count: int,
    wallet_cash_cents: int,
    avg_monthly_bill_cents: int,
) -> Dict[str, Any]:
    score = 680
    score += min(110, max(0, int(paid_on_time_count)) * 12)
    score -= max(0, int(past_due_count)) * 45
    score -= max(0, int(disputed_count)) * 15

    avg_bill = max(1, int(avg_monthly_bill_cents))
    coverage_months = int(wallet_cash_cents) / float(avg_bill)
    if coverage_months >= 2.0:
        score += 40
    elif coverage_months >= 1.0:
        score += 20
    elif wallet_cash_cents <= 0:
        score -= 25

    bounded = max(300, min(850, score))
    grade = "AAA" if bounded >= 780 else ("AA" if bounded >= 700 else ("B" if bounded >= 580 else "CCC_WATCH"))
    return {
        "credit_score": bounded,
        "credit_grade": grade,
        "prepaid_coverage_months": round(coverage_months, 2),
    }
