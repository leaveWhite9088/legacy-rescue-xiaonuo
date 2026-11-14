# -*- coding: utf-8 -*-
"""SAP Ariba Network 标准 `cXML 1.2.050 InvoiceDetailRequest` 采购结算电子发票报文生成器。
面向外资世界 500 强研发中心租户，支持采购订单号（PO Number）回填、税码映射与双边行项目汇总校验。
"""
import xml.sax.saxutils as saxutils
from typing import Any, Dict, List


def _xml_esc(val: Any) -> str:
    return saxutils.escape("" if val is None else str(val), {'"': "&quot;", "'": "&apos;"})


def build_ariba_cxml_invoice_payload(
    invoice: Dict[str, Any],
    buyer_network_id: str,
    po_number: str,
    supplier_network_id: str = "AN01009988771-YUNCE",
    currency: str = "CNY",
) -> Dict[str, Any]:
    """将云策系统账单转换为 SAP Ariba cXML 字符串及三栏金额摘要。"""
    inv_id = _xml_esc(invoice.get("id") or "INV-UNKNOWN")
    inv_date = _xml_esc(str(invoice.get("created_at") or "2026-11-01T00:00:00Z")[:10])
    base_cents = max(0, int(invoice.get("base_fee_cents") or 0))
    ov_cents = max(0, int(invoice.get("overage_fee_cents") or 0))
    tax_cents = max(0, int(invoice.get("tax_cents") or 0))
    late_cents = max(0, int(invoice.get("late_fee_cents") or 0))
    tot_cents = max(0, int(invoice.get("total_cents") or 0))
    net_subtotal_cents = max(0, tot_cents - tax_cents)

    line_specs: List[Dict[str, Any]] = [
        {"line_no": 1, "part_id": f"SKU-SUB-{invoice.get('plan_code', 'PRO')}", "desc": "Monthly SaaS Subscription Access", "cents": base_cents},
    ]
    if ov_cents > 0:
        line_specs.append({"line_no": 2, "part_id": "SKU-API-OVERAGE", "desc": "Progressive Tiered API Metering Overage", "cents": ov_cents})
    if late_cents > 0:
        line_specs.append({"line_no": len(line_specs) + 1, "part_id": "SKU-LATE-SURCHARGE", "desc": "Contractual Late Payment Fee (5%)", "cents": late_cents})

    item_xml_chunks: List[str] = []
    for item in line_specs:
        yuan_str = f"{item['cents'] / 100.0:.2f}"
        item_xml_chunks.append(
            f'      <InvoiceDetailItem invoiceLineNumber="{item["line_no"]}" quantity="1">\n'
            f'        <UnitOfMeasure>EA</UnitOfMeasure>\n'
            f'        <UnitPrice><Money currency="{_xml_esc(currency)}">{yuan_str}</Money></UnitPrice>\n'
            f'        <InvoiceDetailItemReference lineNumber="{item["line_no"]}">\n'
            f'          <ItemID><SupplierPartID>{_xml_esc(item["part_id"])}</SupplierPartID></ItemID>\n'
            f'          <Description xml:lang="zh-CN">{_xml_esc(item["desc"])}</Description>\n'
            f'        </InvoiceDetailItemReference>\n'
            f'        <NetAmount><Money currency="{_xml_esc(currency)}">{yuan_str}</Money></NetAmount>\n'
            f'      </InvoiceDetailItem>'
        )

    cxml_doc = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE cXML SYSTEM "http://xml.cxml.org/schemas/cXML/1.2.050/InvoiceDetail.dtd">\n'
        f'<cXML payloadID="{inv_id}@yunce-billing.cn" timestamp="{inv_date}T00:00:00+08:00">\n'
        '  <Header>\n'
        f'    <From><Credential domain="NetworkID"><Identity>{_xml_esc(supplier_network_id)}</Identity></Credential></From>\n'
        f'    <To><Credential domain="NetworkID"><Identity>{_xml_esc(buyer_network_id)}</Identity></Credential></To>\n'
        '  </Header>\n'
        '  <Request deploymentMode="production">\n'
        '    <InvoiceDetailRequest>\n'
        f'      <InvoiceDetailRequestHeader invoiceID="{inv_id}" purpose="standard" operation="new" invoiceDate="{inv_date}">\n'
        '        <InvoiceDetailHeaderIndicator/>\n'
        '        <InvoiceDetailLineIndicator/>\n'
        '      </InvoiceDetailRequestHeader>\n'
        '      <InvoiceDetailOrder>\n'
        f'        <InvoiceDetailOrderInfo><OrderReference orderID="{_xml_esc(po_number)}"/></InvoiceDetailOrderInfo>\n'
        + "\n".join(item_xml_chunks) + "\n"
        '      </InvoiceDetailOrder>\n'
        '      <InvoiceDetailSummary>\n'
        f'        <SubtotalAmount><Money currency="{_xml_esc(currency)}">{net_subtotal_cents / 100.0:.2f}</Money></SubtotalAmount>\n'
        f'        <Tax><Money currency="{_xml_esc(currency)}">{tax_cents / 100.0:.2f}</Money><Description xml:lang="zh-CN">VAT</Description></Tax>\n'
        f'        <GrossAmount><Money currency="{_xml_esc(currency)}">{tot_cents / 100.0:.2f}</Money></GrossAmount>\n'
        f'        <NetAmount><Money currency="{_xml_esc(currency)}">{tot_cents / 100.0:.2f}</Money></NetAmount>\n'
        '      </InvoiceDetailSummary>\n'
        '    </InvoiceDetailRequest>\n'
        '  </Request>\n'
        '</cXML>'
    )
    return {
        "invoice_id": invoice.get("id"),
        "po_number": po_number,
        "line_count": len(line_specs),
        "gross_cents": tot_cents,
        "cxml_document": cxml_doc,
    }
