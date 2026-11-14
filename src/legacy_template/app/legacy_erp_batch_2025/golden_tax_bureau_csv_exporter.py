# -*- coding: utf-8 -*-
"""电子税务局数电票批量开票导入模板（32 列标准制表符/CSV 双格式）序列化与税率税收分类编码校验器。
税收分类编码规范：
- `3040201010000000000`：现代服务*信息技术服务*软件服务（SaaS 基础订阅）
- `3040201020000000000`：现代服务*信息技术服务*信息系统增值评测服务（API 弹性超额计量）
- 违约滞纳金随同主服务价外费用一并按 6% 税目开具或开具普通收据（依合同约定）。
"""
import csv
import io
from typing import Any, Dict, List


GOODS_TAX_CLASS_CODES: Dict[str, Dict[str, str]] = {
    "SUBSCRIPTION_BASE": {
        "tax_class_code": "3040201010000000000",
        "item_short_name": "*信息技术服务*云策SaaS订阅服务费",
        "unit": "月",
    },
    "API_OVERAGE_USAGE": {
        "tax_class_code": "3040201020000000000",
        "item_short_name": "*信息技术服务*API弹性调用超额费",
        "unit": "批",
    },
    "LATE_SURCHARGE": {
        "tax_class_code": "3040201990000000000",
        "item_short_name": "*信息技术服务*逾期结算违约滞纳金",
        "unit": "项",
    },
}

BUREAU_EXPORT_HEADERS = [
    "单据号", "发票类型", "购买方名称", "购买方纳税人识别号", "购买方地址电话",
    "购买方开户行及账号", "商品或服务名称", "税收分类编码", "规格型号", "单位",
    "数量", "含税标志", "单价(元)", "金额(元)", "税率", "税额(元)", "备注",
]


def validate_cn_taxpayer_id_format(tax_id: str) -> bool:
    clean = (tax_id or "").strip().upper()
    if len(clean) not in (15, 18, 20):
        return False
    return all(ch.isalnum() for ch in clean)


def export_golden_tax_batch_import_csv(
    requests: List[Dict[str, Any]],
    default_vat_rate_bps: int = 600,
) -> Dict[str, Any]:
    """将待开票申请列表转换为电子税务局客户端可直接批量导入的 UTF-8 CSV 文本。"""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(BUREAU_EXPORT_HEADERS)

    exported_rows = 0
    skipped_errors: List[str] = []
    total_gross_cents = 0
    total_tax_cents = 0

    rate_dec_str = f"{default_vat_rate_bps / 10000.0:.2f}"

    for idx, req in enumerate(requests, start=1):
        doc_no = str(req.get("id") or f"FP-BATCH-{idx:04d}")
        buyer_name = str(req.get("buyer_name") or req.get("title") or "").strip()
        tax_id = str(req.get("buyer_tax_id") or "").strip()
        f_type = str(req.get("fapiao_type") or "VAT_SPECIAL_E")

        if not buyer_name:
            skipped_errors.append(f"{doc_no}:MISSING_BUYER_NAME")
            continue
        if f_type == "VAT_SPECIAL_E" and not validate_cn_taxpayer_id_format(tax_id):
            skipped_errors.append(f"{doc_no}:INVALID_BUYER_TAX_ID:{tax_id}")
            continue

        gross_c = max(0, int(req.get("gross_amount_cents") or 0))
        tax_c = max(0, int(req.get("tax_amount_cents") or 0))
        net_c = max(0, gross_c - tax_c)
        if gross_c <= 0:
            skipped_errors.append(f"{doc_no}:NON_POSITIVE_GROSS")
            continue

        cat = GOODS_TAX_CLASS_CODES["SUBSCRIPTION_BASE"]
        f_label = "数电专票" if f_type == "VAT_SPECIAL_E" else "数电普票"
        memo = f"对应账单:{req.get('invoice_id', '-')};账期:{req.get('period_key', '2026-11')}"

        writer.writerow([
            doc_no,
            f_label,
            buyer_name,
            tax_id,
            str(req.get("buyer_addr_tel") or ""),
            str(req.get("buyer_bank_acct") or ""),
            cat["item_short_name"],
            cat["tax_class_code"],
            str(req.get("plan_code") or "STANDARD"),
            cat["unit"],
            "1",
            "否(不含税单价)",
            f"{net_c / 100.0:.2f}",
            f"{net_c / 100.0:.2f}",
            rate_dec_str,
            f"{tax_c / 100.0:.2f}",
            memo,
        ])
        exported_rows += 1
        total_gross_cents += gross_c
        total_tax_cents += tax_c

    return {
        "exported_row_count": exported_rows,
        "skipped_errors": skipped_errors,
        "total_gross_cents": total_gross_cents,
        "total_tax_cents": total_tax_cents,
        "csv_text": buf.getvalue(),
    }
