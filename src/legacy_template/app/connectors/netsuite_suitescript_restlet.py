# -*- coding: utf-8 -*-
"""Oracle NetSuite SuiteScript 2.1 RESTlet 应收发票（Invoice）与红字贷项通知单（CreditMemo）双向报文转换器。"""
from typing import Any, Dict, List


NETSUITE_SUBSIDIARY_MAP: Dict[str, int] = {
    "CN_VAT_6_INCLUSIVE": 101,   # 云策智算（上海）主体
    "CN_VAT_6_EXCLUSIVE": 101,
    "EXEMPT": 102,               # 云策香港国际主体
    "SG_GST_9_EXCLUSIVE": 103,   # YunCe Singapore Pte. Ltd.
}

NETSUITE_TAX_CODE_INTERNAL_IDS: Dict[str, int] = {
    "CN_VAT_6_INCLUSIVE": 3006,
    "CN_VAT_6_EXCLUSIVE": 3007,
    "SG_GST_9_EXCLUSIVE": 4009,
    "EXEMPT": 1000,
}


def build_netsuite_invoice_restlet_payload(
    invoice: Dict[str, Any],
    tax_profile_code: str = "CN_VAT_6_INCLUSIVE",
) -> Dict[str, Any]:
    sub_id = NETSUITE_SUBSIDIARY_MAP.get(tax_profile_code, 101)
    tax_id = NETSUITE_TAX_CODE_INTERNAL_IDS.get(tax_profile_code, 3006)
    base_c = max(0, int(invoice.get("base_fee_cents") or 0))
    ov_c = max(0, int(invoice.get("overage_fee_cents") or 0))
    late_c = max(0, int(invoice.get("late_fee_cents") or 0))
    tax_c = max(0, int(invoice.get("tax_cents") or 0))

    item_list: List[Dict[str, Any]] = [
        {
            "item_external_id": f"SAAS_{invoice.get('plan_code', 'STARTER')}",
            "quantity": 1,
            "rate_yuan": round(base_c / 100.0, 2),
            "tax_code_internal_id": tax_id,
            "rev_rec_rule": "RATABLE_MONTHLY",
        }
    ]
    if ov_c > 0:
        item_list.append({
            "item_external_id": "API_METERED_OVERAGE",
            "quantity": 1,
            "rate_yuan": round(ov_c / 100.0, 2),
            "tax_code_internal_id": tax_id,
            "rev_rec_rule": "AS_INVOICED_USAGE",
        })
    if late_c > 0:
        item_list.append({
            "item_external_id": "FIN_LATE_FEE_5PCT",
            "quantity": 1,
            "rate_yuan": round(late_c / 100.0, 2),
            "tax_code_internal_id": 1000,
            "rev_rec_rule": "IMMEDIATE_PENALTY",
        })

    return {
        "recordType": "invoice",
        "externalId": f"YC_{invoice.get('id')}",
        "entityExternalId": str(invoice.get("tenant_id") or ""),
        "subsidiaryInternalId": sub_id,
        "postingPeriodName": str(invoice.get("period_key") or "2026-11"),
        "currencyIso": "SGD" if tax_profile_code == "SG_GST_9_EXCLUSIVE" else "CNY",
        "expectedTaxYuan": round(tax_c / 100.0, 2),
        "itemList": item_list,
    }


def build_netsuite_adjustment_credit_memo_payload(adjustment: Dict[str, Any]) -> Dict[str, Any]:
    delta = int(adjustment.get("delta_cents") or 0)
    rec_type = "creditmemo" if delta < 0 else "debitmemo_journal"
    return {
        "recordType": rec_type,
        "externalId": f"YC_ADJ_{adjustment.get('id')}",
        "entityExternalId": str(adjustment.get("tenant_id") or ""),
        "appliedPostingPeriod": str(adjustment.get("applied_period_key") or "2026-11"),
        "priorClosedPeriodReferenced": str(adjustment.get("target_period_key") or ""),
        "originInvoiceId": str(adjustment.get("ref_invoice_id") or ""),
        "absoluteAmountYuan": round(abs(delta) / 100.0, 2),
        "memo": str(adjustment.get("reason") or ""),
    }
