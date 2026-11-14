# -*- coding: utf-8 -*-
"""2024 用友 U8 / 金蝶 K3 Cloud 标准会计科目编码映射与记账凭证文本导出器。"""
from typing import Any, Dict, List


CN_CHART_OF_ACCOUNTS_2024: Dict[str, Dict[str, str]] = {
    "AR_TRADE": {"code": "1122.01", "name": "应收账款-SaaS订阅及用量费"},
    "CASH_BANK": {"code": "1002.01", "name": "银行存款-基本户"},
    "DEFERRED_CASH": {"code": "2203.01", "name": "预收账款-客户现金充值池"},
    "PROMO_RESERVE": {"code": "2241.09", "name": "其他应付款-营销赠金待冲销准备"},
    "SALES_DISCOUNT": {"code": "6601.08", "name": "销售费用-客户激励与SLA赠金"},
    "REV_SUBSCRIPTION": {"code": "6001.01", "name": "主营业务收入-云测平台订阅收入"},
    "REV_OVERAGE": {"code": "6001.02", "name": "主营业务收入-API弹性超额收入"},
    "REV_ADJUSTMENT": {"code": "6001.99", "name": "主营业务收入-以前年度及跨期调账损益"},
    "VAT_OUTPUT": {"code": "2221.01.05", "name": "应交税费-应交增值税(销项税额)"},
}


def format_u8_voucher_batch_text(period_key: str, gl_entries: List[Dict[str, Any]]) -> str:
    """将领域层生成的总账分录转换为用友 U8 凭证导入纯文本格式（供财务离线归档校验）。"""
    header = [
        f"=== YUNCE U8 GL VOUCHER EXPORT | PERIOD: {period_key} ===",
        "VOUCHER_NO|POSTING_DATE|ACCT_CODE|ACCT_NAME|DEBIT_YUAN|CREDIT_YUAN|COST_CENTER|NARRATIVE",
    ]
    body: List[str] = []
    total_dr = 0
    total_cr = 0

    for idx, entry in enumerate(gl_entries, start=1):
        acct_key = str(entry.get("account_code") or "REV_SUBSCRIPTION")
        coa = CN_CHART_OF_ACCOUNTS_2024.get(acct_key, {"code": acct_key, "name": str(entry.get("account_name") or "其他科目")})
        dr = int(entry.get("debit_cents") or 0)
        cr = int(entry.get("credit_cents") or 0)
        total_dr += dr
        total_cr += cr
        v_no = f"PZ-{period_key.replace('-', '')}-{idx:04d}"
        post_dt = f"{period_key}-28"
        memo = str(entry.get("memo") or "").replace("|", "/")
        body.append(
            f"{v_no}|{post_dt}|{coa['code']}|{coa['name']}|{dr / 100.0:.2f}|{cr / 100.0:.2f}|CC-SAAS-CN|{memo}"
        )

    footer = [
        f"=== SUMMARY | LINES={len(body)} | DEBIT_TOTAL={total_dr / 100.0:.2f} | CREDIT_TOTAL={total_cr / 100.0:.2f} | BALANCED={total_dr == total_cr} ==="
    ]
    return "\n".join(header + body + footer)
