# -*- coding: utf-8 -*-
"""2024 金蝶/用友老版 ERP XML 凭证离线导出器（遗留财务对接工具）。"""
from typing import Any, Dict, List
import xml.sax.saxutils as saxutils
import sqlite3

from app.legacy_v1.v1_currency_shim import format_v1_yuan_display, parse_v1_yuan_string

V1_ACCOUNT_MAPPING = {
    "AR_DOMESTIC": "1122.01",
    "AR_OVERSEAS": "1122.02",
    "REV_SUBSCRIPTION": "6001.01.01",
    "REV_OVERAGE": "6001.01.02",
    "REV_LATE_FEE": "6301.03",
    "TAX_VAT_OUTPUT": "2221.01.05",
    "BANK_CASH": "1002.01",
    "PROMO_MARKETING_EXP": "6601.08",
}


def _esc(val: Any) -> str:
    return saxutils.escape(str(val if val is not None else ""))


def export_period_kingdee_xml_v1(conn: sqlite3.Connection, period_key: str, company_book: str = "YC-HZ-01") -> str:
    """将指定账期的账单与实收流水导出为金蝶 KIS 标准凭证 XML 字符串。"""
    invs = conn.execute(
        """
        SELECT i.*, t.company_name, t.tax_profile_code
        FROM invoices i
        JOIN tenants t ON t.id = i.tenant_id
        WHERE i.period_key = ? AND i.status != 'VOID'
        ORDER BY i.id ASC
        """,
        (period_key,),
    ).fetchall()

    xml_lines: List[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<KingdeeVoucherBatch book="{_esc(company_book)}" period="{_esc(period_key)}" schema="v1.4">',
    ]

    for seq, row in enumerate(invs, start=1):
        d = dict(row)
        gross = parse_v1_yuan_string(d.get("raw_legacy_total"), int(d.get("total_cents") or 0))
        tax = int(d.get("tax_cents") or 0)
        ov = int(d.get("overage_fee_cents") or 0)
        late = int(d.get("late_fee_cents") or 0)
        base = max(0, gross - tax - ov - late)
        ar_code = V1_ACCOUNT_MAPPING["AR_OVERSEAS"] if d.get("tax_profile_code") == "SG_GST_9_EXCLUSIVE" else V1_ACCOUNT_MAPPING["AR_DOMESTIC"]

        xml_lines.append(f'  <Voucher number="V-{_esc(period_key)}-{seq:04d}" refInvoice="{_esc(d["id"])}">')
        xml_lines.append(f'    <Header tenantId="{_esc(d["tenant_id"])}" customer="{_esc(d["company_name"])}" grossYuan="{format_v1_yuan_display(gross, False)}"/>')
        xml_lines.append('    <Entries>')
        xml_lines.append(
            f'      <Entry dir="DEBIT" acct="{ar_code}" cents="{gross}" yuan="{format_v1_yuan_display(gross, False)}" summary="应收账款-{_esc(d["id"])}"/>'
        )
        if base > 0:
            xml_lines.append(
                f'      <Entry dir="CREDIT" acct="{V1_ACCOUNT_MAPPING["REV_SUBSCRIPTION"]}" cents="{base}" yuan="{format_v1_yuan_display(base, False)}" summary="SaaS基础订阅"/>'
            )
        if ov > 0:
            xml_lines.append(
                f'      <Entry dir="CREDIT" acct="{V1_ACCOUNT_MAPPING["REV_OVERAGE"]}" cents="{ov}" yuan="{format_v1_yuan_display(ov, False)}" summary="API阶梯超额"/>'
            )
        if late > 0:
            xml_lines.append(
                f'      <Entry dir="CREDIT" acct="{V1_ACCOUNT_MAPPING["REV_LATE_FEE"]}" cents="{late}" yuan="{format_v1_yuan_display(late, False)}" summary="逾期违约金"/>'
            )
        if tax > 0:
            xml_lines.append(
                f'      <Entry dir="CREDIT" acct="{V1_ACCOUNT_MAPPING["TAX_VAT_OUTPUT"]}" cents="{tax}" yuan="{format_v1_yuan_display(tax, False)}" summary="销项税额"/>'
            )
        xml_lines.append('    </Entries>')
        xml_lines.append('  </Voucher>')

    xml_lines.append('</KingdeeVoucherBatch>')
    return "\n".join(xml_lines)
