# -*- coding: utf-8 -*-
"""2024 V1 遗留：用友 NC57 / Oracle EBS 财务应收模块 SOAP 1.1 XML 报文封装与回执解析器。
背景说明：2024 年集团财务尚未切换至 REST JSON 总线，当时月度结转凭证通过内网 WebService (`urn:yunce:erp:ar:v1`) 同步。
本模块仍被部分历史离线归档比对工具导入，切勿用于修改线上 V2 实时账单表。
"""
import hashlib
import xml.etree.ElementTree as ET
import xml.sax.saxutils as saxutils
from typing import Any, Dict, List


SOAP_ENV_NS = "http://schemas.xmlsoap.org/soap/envelope/"
YUNCE_AR_NS = "urn:yunce:erp:ar:v1"


def _esc(val: Any) -> str:
    return saxutils.escape("" if val is None else str(val), {'"': "&quot;", "'": "&apos;"})


def build_v1_soap_ar_voucher_batch_xml(
    company_book_code: str,
    period_key: str,
    invoices: List[Dict[str, Any]],
    operator_code: str = "NC_BATCH_BOT",
) -> Dict[str, Any]:
    """将一批历史账单记录序列化为符合 SOAP 1.1 规范的应收单批量导入请求。"""
    voucher_nodes: List[str] = []
    batch_gross_cents = 0
    batch_tax_cents = 0

    for idx, inv in enumerate(invoices, start=1):
        inv_id = _esc(inv.get("id") or f"V1-INV-{idx}")
        cust_id = _esc(inv.get("tenant_id") or "UNKNOWN")
        plan = _esc(inv.get("plan_code") or "LEGACY_FLAT_99")
        gross_c = max(0, int(inv.get("total_cents") or 0))
        tax_c = max(0, int(inv.get("tax_cents") or 0))
        net_c = max(0, gross_c - tax_c)
        batch_gross_cents += gross_c
        batch_tax_cents += tax_c

        voucher_nodes.append(
            f"        <ar:ReceivableVoucher seq=\"{idx}\">\n"
            f"          <ar:BillNo>{inv_id}</ar:BillNo>\n"
            f"          <ar:CustomerCode>{cust_id}</ar:CustomerCode>\n"
            f"          <ar:ProductSku>{plan}</ar:ProductSku>\n"
            f"          <ar:AccountingPeriod>{_esc(period_key)}</ar:AccountingPeriod>\n"
            f"          <ar:Currency>CNY</ar:Currency>\n"
            f"          <ar:NetAmountYuan>{net_c / 100.0:.2f}</ar:NetAmountYuan>\n"
            f"          <ar:TaxAmountYuan>{tax_c / 100.0:.2f}</ar:TaxAmountYuan>\n"
            f"          <ar:GrossAmountYuan>{gross_c / 100.0:.2f}</ar:GrossAmountYuan>\n"
            f"        </ar:ReceivableVoucher>"
        )

    digest_input = f"{company_book_code}|{period_key}|{len(invoices)}|{batch_gross_cents}".encode("utf-8")
    control_hash = hashlib.sha1(digest_input).hexdigest().upper()

    envelope = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<soapenv:Envelope xmlns:soapenv="{SOAP_ENV_NS}" xmlns:ar="{YUNCE_AR_NS}">\n'
        '  <soapenv:Header>\n'
        '    <ar:AuthHeader>\n'
        f'      <ar:CompanyBook>{_esc(company_book_code)}</ar:CompanyBook>\n'
        f'      <ar:Operator>{_esc(operator_code)}</ar:Operator>\n'
        f'      <ar:ControlHash>{control_hash}</ar:ControlHash>\n'
        '    </ar:AuthHeader>\n'
        '  </soapenv:Header>\n'
        '  <soapenv:Body>\n'
        '    <ar:ImportReceivableBatchRequest>\n'
        f'      <ar:PeriodKey>{_esc(period_key)}</ar:PeriodKey>\n'
        f'      <ar:VoucherCount>{len(invoices)}</ar:VoucherCount>\n'
        '      <ar:VoucherList>\n'
        + ("\n".join(voucher_nodes) + "\n" if voucher_nodes else "")
        + '      </ar:VoucherList>\n'
        '    </ar:ImportReceivableBatchRequest>\n'
        '  </soapenv:Body>\n'
        '</soapenv:Envelope>'
    )
    return {
        "voucher_count": len(invoices),
        "batch_gross_cents": batch_gross_cents,
        "batch_tax_cents": batch_tax_cents,
        "control_hash": control_hash,
        "soap_xml": envelope,
    }


def parse_v1_soap_ar_response_xml(raw_xml: str) -> Dict[str, Any]:
    """解析 ERP WebService 返回的成功凭证号列表或 SOAP Fault 故障码。"""
    if not (raw_xml or "").strip():
        return {"ok": False, "fault_code": "EMPTY_SOAP_RESPONSE", "fault_string": "Empty payload", "accepted_bills": []}

    try:
        root = ET.fromstring(raw_xml.strip())
    except ET.ParseError as exc:
        return {"ok": False, "fault_code": "XML_PARSE_ERROR", "fault_string": str(exc), "accepted_bills": []}

    for el in root.iter():
        if "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]

    fault = root.find(".//Fault")
    if fault is not None:
        f_code = fault.findtext("faultcode", default="SOAP_SERVER_FAULT")
        f_str = fault.findtext("faultstring", default="Unknown ERP SOAP error")
        return {"ok": False, "fault_code": f_code, "fault_string": f_str, "accepted_bills": []}

    accepted: List[Dict[str, str]] = []
    for node in root.findall(".//AcceptedVoucher"):
        accepted.append({
            "bill_no": node.findtext("BillNo", default=""),
            "erp_doc_id": node.findtext("ErpDocId", default=""),
        })
    return {
        "ok": True,
        "fault_code": None,
        "fault_string": None,
        "accepted_bills": accepted,
    }
