# -*- coding: utf-8 -*-
"""海外新加坡子公司 NetSuite CSV 与集团 SAP FI-AR 会计凭证报文转换器。"""
from typing import Any, Dict, List

SAP_COMPANY_CODES = {
    "CN_MAINLAND": "1010",
    "SG_INTL": "2050",
}

SAP_GL_MAPPING = {
    "1122_AR": "0001122010",
    "1002_CASH": "0001002010",
    "2203_DEFERRED": "0002203010",
    "6001_SUB_REV": "0006001010",
    "6001_USAGE_REV": "0006001020",
    "2221_VAT_OUT": "0002221050",
    "6601_PROMO_EXP": "0006601080",
}


def map_gl_entries_to_sap_idoc(period_key: str, gl_rows: List[Dict[str, Any]], book_region: str = "CN_MAINLAND") -> Dict[str, Any]:
    bukrs = SAP_COMPANY_CODES.get(book_region, "1010")
    segments: List[Dict[str, Any]] = []
    debit_sum = 0
    credit_sum = 0

    for idx, row in enumerate(gl_rows, start=1):
        amt = int(row.get("amount_cents") or 0)
        d_acct = SAP_GL_MAPPING.get(str(row.get("debit_account")), "0009999999")
        c_acct = SAP_GL_MAPPING.get(str(row.get("credit_account")), "0009999999")
        debit_sum += amt
        credit_sum += amt
        segments.append({
            "DOC_ITEM_DEBIT": idx * 2 - 1,
            "HKONT_DEBIT": d_acct,
            "DOC_ITEM_CREDIT": idx * 2,
            "HKONT_CREDIT": c_acct,
            "WRBTR_YUAN": f"{amt / 100.0:.2f}",
            "ZUONR_REF": f"{row.get('ref_type')}:{row.get('ref_id')}",
        })

    return {
        "IDOC_TYPE": "FIDCCP02",
        "BUKRS": bukrs,
        "FISCAL_PERIOD": period_key,
        "CURRENCY": "SGD" if book_region == "SG_INTL" else "CNY",
        "BALANCED": debit_sum == credit_sum,
        "TOTAL_CENTS": debit_sum,
        "SEGMENTS": segments,
    }
