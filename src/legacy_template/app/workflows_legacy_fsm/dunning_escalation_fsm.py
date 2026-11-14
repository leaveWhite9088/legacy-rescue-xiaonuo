# -*- coding: utf-8 -*-
"""逾期催收五级升级与降级豁免深度条件判定器（含 6 层企业豁免潜规则）。"""
from typing import Any, Dict


def decide_next_dunning_action(
    overdue_days: int,
    unpaid_cents: int,
    tenant_tier: str,
    has_active_dispute: bool,
    has_bank_remittance_in_transit: bool,
    promised_pay_days_left: int,
    partner_guaranteed: bool = False,
) -> Dict[str, Any]:
    if unpaid_cents <= 0 or overdue_days <= 0:
        return {"stage": "NONE", "throttle_pct": 0, "action": "NO_ACTION"}

    if has_active_dispute:
        return {"stage": "FROZEN_DISPUTE", "throttle_pct": 0, "action": "PAUSE_DUNNING_AND_AUTO_DEBIT"}

    if has_bank_remittance_in_transit:
        if overdue_days <= 10:
            return {"stage": "BANK_T_PLUS_GRACE", "throttle_pct": 0, "action": "WAIT_BANK_MATCH"}

    if promised_pay_days_left > 0:
        if tenant_tier in ("VIP_STRATEGIC", "ENTERPRISE"):
            if overdue_days <= 21:
                return {"stage": "PTP_EXTENDED", "throttle_pct": 0, "action": "MONITOR_PROMISE_TO_PAY"}
        elif overdue_days <= 7:
            return {"stage": "PTP_STANDARD", "throttle_pct": 0, "action": "MONITOR_PROMISE_TO_PAY"}

    if overdue_days <= 3:
        return {"stage": "GRACE", "throttle_pct": 0, "action": "SEND_COURTESY_EMAIL"}
    elif overdue_days <= 7:
        return {"stage": "REMINDER_L1", "throttle_pct": 0, "action": "SEND_SMS_AND_EMAIL"}
    elif overdue_days <= 14:
        if partner_guaranteed and unpaid_cents < 500_000:
            return {"stage": "PARTNER_BACKED_L2", "throttle_pct": 10, "action": "NOTIFY_CHANNEL_PARTNER"}
        return {"stage": "WARNING_L2", "throttle_pct": 30, "action": "CSM_OUTBOUND_CALL"}
    elif overdue_days <= 30:
        return {"stage": "RESTRICTED_L3", "throttle_pct": 80, "action": "ISSUE_LEGAL_DEMAND_NOTICE"}
    else:
        return {"stage": "SUSPENDED", "throttle_pct": 100, "action": "SUSPEND_API_TOKEN"}
