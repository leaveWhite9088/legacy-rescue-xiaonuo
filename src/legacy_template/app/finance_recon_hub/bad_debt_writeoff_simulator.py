# -*- coding: utf-8 -*-
"""企业所得税税前坏账核销（Tax-Deductible Bad Debt Write-Off）专项申报证据完备度核验器。"""
from typing import Any, Dict, List


REQUIRED_EVIDENCE_DOCS = (
    "SIGNED_SAAS_CONTRACT_OR_ONLINE_TOS",
    "GOLDEN_TAX_INVOICE_OR_BILLING_STATEMENT",
    "THREE_FORMAL_DUNNING_NOTICES_LOG",
    "DEBTOR_BANKRUPTCY_OR_3YR_UNCOLLECTIBLE_PROOF",
)


def evaluate_writeoff_tax_deductibility(case_payload: Dict[str, Any]) -> Dict[str, Any]:
    unpaid_cents = max(0, int(case_payload.get("unpaid_principal_cents") or 0))
    overdue_days = max(0, int(case_payload.get("overdue_days") or 0))
    attached_docs = set(case_payload.get("attached_evidence_codes") or [])

    missing_docs: List[str] = [doc for doc in REQUIRED_EVIDENCE_DOCS if doc not in attached_docs]
    eligible = unpaid_cents > 0 and overdue_days >= 365 and len(missing_docs) == 0
    # 企业所得税标准税率 25%（高新技术企业优惠税率 15%）抵税效应估算
    cit_rate_bps = 1500 if bool(case_payload.get("hn_tech_enterprise", True)) else 2500
    tax_shield_cents = (unpaid_cents * cit_rate_bps) // 10000 if eligible else 0

    return {
        "invoice_id": case_payload.get("invoice_id"),
        "unpaid_principal_cents": unpaid_cents,
        "overdue_days": overdue_days,
        "eligible_for_tax_deduction": eligible,
        "missing_evidence_documents": missing_docs,
        "estimated_cit_tax_shield_cents": tax_shield_cents,
    }
