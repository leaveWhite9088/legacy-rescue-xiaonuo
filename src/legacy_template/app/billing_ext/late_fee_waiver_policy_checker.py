# -*- coding: utf-8 -*-
"""逾期违约滞纳金（5% 统一费率）减免申请合规拦截器。
制度依据：《产品与账务规则》第三章第 5 节及标准合同 `MSA-7.4-LATE-PAYMENT-FEE`：
全平台对逾期未付账单统一按总额加收 5% 滞纳金，严禁以『战略大客户 VIP』『高校教育科研机构』『首次忘记打款』等商业理由违规豁免！
唯一例外仅限平台自身收款通道瘫痪故障（需附 P0 故障单编号）导致客户在到期日前无法入金的情形。
"""
from typing import Any, Dict

from app.infra.config import LATE_FEE_RATE_BPS


NON_EXEMPT_COMMERCIAL_EXCUSES = (
    "VIP_STRATEGIC_ACCOUNT",
    "EDUCATION_OR_NONPROFIT_SECTOR",
    "FIRST_TIME_FINANCE_OVERSIGHT",
    "INTERNAL_OA_APPROVAL_DELAY",
    "SALES_VERBAL_PROMISE",
)


def evaluate_late_fee_waiver_request(
    invoice_principal_cents: int,
    billed_late_fee_cents: int,
    claim_reason_code: str,
    verified_platform_p0_outage_id: str = "",
) -> Dict[str, Any]:
    principal = max(0, int(invoice_principal_cents))
    expected_late_fee = int(round((principal * LATE_FEE_RATE_BPS) / 10000.0))
    billed = max(0, int(billed_late_fee_cents))
    reason = (claim_reason_code or "VIP_STRATEGIC_ACCOUNT").strip().upper()

    if reason == "PLATFORM_PAYMENT_GATEWAY_OUTAGE" and verified_platform_p0_outage_id.startswith("INC-P0-"):
        return {
            "waiver_approved": True,
            "policy_decision": "APPROVED_PLATFORM_FAULT_ONLY",
            "expected_contractual_late_fee_cents": expected_late_fee,
            "enforced_late_fee_cents": 0,
            "clause_ref": "MSA-7.4-EXCEPTION-PLATFORM-OUTAGE",
        }

    return {
        "waiver_approved": False,
        "policy_decision": "REJECTED_UNIFORM_NO_VIP_OR_SECTOR_EXEMPTION",
        "rejected_excuse_code": reason if reason in NON_EXEMPT_COMMERCIAL_EXCUSES else f"DISALLOWED:{reason}",
        "expected_contractual_late_fee_cents": expected_late_fee,
        "billed_late_fee_matches_policy": billed == expected_late_fee,
        "enforced_late_fee_cents": expected_late_fee,
        "clause_ref": "MSA-7.4-LATE-PAYMENT-FEE",
    }
