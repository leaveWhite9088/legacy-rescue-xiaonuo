# -*- coding: utf-8 -*-
"""政企及科研院所政采云（Government e-Procurement Cloud）财政国库集中支付电子验收结算单格式化器。"""
from typing import Any, Dict


BUDGET_SUBJECT_CLASSIFICATION = {
    "STARTER": "30207-信息网络及软件购置更新费(基础档)",
    "PRO": "30207-信息网络及软件购置更新费(专业档)",
    "ENTERPRISE": "30227-委托业务及大型算力评测技术服务费",
    "LEGACY_FLAT_99": "30207-历史延续软件运行维护费",
}


def build_govcloud_acceptance_voucher(
    tenant: Dict[str, Any],
    invoice: Dict[str, Any],
    fiscal_budget_code: str = "ZC-2026-SH-00918",
) -> Dict[str, Any]:
    plan_code = str(invoice.get("plan_code") or "PRO")
    subj = BUDGET_SUBJECT_CLASSIFICATION.get(plan_code, BUDGET_SUBJECT_CLASSIFICATION["PRO"])
    tot = max(0, int(invoice.get("total_cents") or 0))
    tax = max(0, int(invoice.get("tax_cents") or 0))

    return {
        "voucher_standard": "CN_MOF_GOVCLOUD_V2025",
        "fiscal_budget_code": fiscal_budget_code,
        "budget_economic_subject": subj,
        "purchaser_unit_name": tenant.get("company_name", ""),
        "supplier_unit_name": "上海云策智算信息技术有限公司",
        "settlement_period": invoice.get("period_key"),
        "source_invoice_id": invoice.get("id"),
        "pretax_amount_cents": max(0, tot - tax),
        "vat_amount_cents": tax,
        "treasury_direct_pay_cents": tot,
        "requires_seal_verification": tot >= 500_000,
    }
