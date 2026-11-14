# -*- coding: utf-8 -*-
"""中英双语商业账单（Commercial Invoice）与电子收款回执 Markdown/纯文本渲染器。"""
from typing import Any, Dict, List


def render_bilingual_invoice_markdown(
    invoice: Dict[str, Any],
    tenant: Dict[str, Any],
    line_items: List[Dict[str, Any]],
) -> str:
    """供客服工单附件导出与企业客户财务报销附件下载使用的双语账单文本。"""
    inv_id = str(invoice.get("id") or "-")
    comp = str(tenant.get("company_name") or invoice.get("tenant_id") or "-")
    period = str(invoice.get("period_key") or "-")
    plan = str(invoice.get("plan_code") or "-")
    status = str(invoice.get("status") or "-")

    lines = [
        f"# 云测智算商业账单 / YunCe Cloud Commercial Invoice ({inv_id})",
        "",
        f"- **客户名称 / Customer**: {comp} (`{invoice.get('tenant_id')}`)",
        f"- **结算账期 / Billing Period**: `{period}` ({invoice.get('cycle_start')} ~ {invoice.get('cycle_end')})",
        f"- **计费套餐 / Subscription Plan**: `{plan}`",
        f"- **单据状态 / Status**: `{status}`",
        "",
        "## 费用明细 / Charge Breakdown",
        "",
        "| 行号 | 费用项目 / Description | 数量 / Qty | 金额 (RMB) |",
        "| --- | --- | ---: | ---: |",
    ]

    if line_items:
        for idx, item in enumerate(line_items, start=1):
            amt_yuan = int(item.get("amount_cents") or 0) / 100.0
            lines.append(f"| {idx} | {item.get('title', 'Service Fee')} | {item.get('quantity', 1)} | ¥{amt_yuan:,.2f} |")
    else:
        base_y = int(invoice.get("base_fee_cents") or 0) / 100.0
        ov_y = int(invoice.get("overage_fee_cents") or 0) / 100.0
        tax_y = int(invoice.get("tax_cents") or 0) / 100.0
        lines.append(f"| 1 | 月度套餐订阅费 / Monthly Base Subscription | 1 | ¥{base_y:,.2f} |")
        lines.append(f"| 2 | API 弹性超额阶梯费 / Tiered API Overage | - | ¥{ov_y:,.2f} |")
        lines.append(f"| 3 | 增值税销项税额 / VAT Surcharge | - | ¥{tax_y:,.2f} |")

    tot_y = int(invoice.get("total_cents") or 0) / 100.0
    paid_y = int(invoice.get("paid_cents") or 0) / 100.0
    ref_y = int(invoice.get("refunded_cents") or 0) / 100.0
    lines.extend([
        "",
        f"- **账单应付总额 / Total Due**: `¥{tot_y:,.2f}`",
        f"- **累计已付金额 / Total Paid**: `¥{paid_y:,.2f}`",
        f"- **累计已退金额 / Total Refunded**: `¥{ref_y:,.2f}`",
    ])
    return "\n".join(lines)
