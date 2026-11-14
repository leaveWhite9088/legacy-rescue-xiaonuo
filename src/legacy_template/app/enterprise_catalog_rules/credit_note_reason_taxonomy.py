# -*- coding: utf-8 -*-
"""财务跨期调账单（`billing_adjustments`）标准原因分类码与会计科目映射规范。"""
from typing import Dict


ADJUSTMENT_REASON_TAXONOMY: Dict[str, Dict[str, str]] = {
    "CLOSED_PERIOD_RATING_ERROR_CREDIT": {
        "direction": "NEGATIVE_CREDIT_TO_CUSTOMER",
        "gl_account": "6001.99_PRIOR_PERIOD_REV_ADJ",
        "requires_closed_period_ref": "TRUE",
    },
    "LATE_GATEWAY_USAGE_TRUEUP_DEBIT": {
        "direction": "POSITIVE_DEBIT_TO_CUSTOMER",
        "gl_account": "6001.02_USAGE_OVERAGE_TRUEUP",
        "requires_closed_period_ref": "TRUE",
    },
    "SLA_UPTIME_BREACH_PROMO_COMP": {
        "direction": "PROMO_GRANT_NON_CASH",
        "gl_account": "6601.08_SLA_PROMO_EXPENSE",
        "requires_closed_period_ref": "FALSE",
    },
}
