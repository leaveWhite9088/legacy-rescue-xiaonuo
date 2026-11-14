# -*- coding: utf-8 -*-
"""用友 NC65 / YonBIP 外部交换平台（UFP External Exchange）会计凭证 XML 报文双边借贷校验与辅助核算项检查器。
内控规范：
1. 凡涉及 `1122`（应收账款）与 `2203`（合同负债/预收账款）科目的凭证行，必须挂接【客商辅助核算档案号】；
2. 同一张会计凭证内所有借方分录之和必须严格等于所有贷方分录之和，任何单边悬空凭证禁止投递用友网关。
"""
import xml.etree.ElementTree as ET
from typing import Any, Dict, List


CUSTOMER_AUX_REQUIRED_PREFIXES = ("1122", "2203")


def build_ufinterface_gl_voucher_xml(
    voucher_id: str,
    accounting_year: str,
    accounting_month: str,
    lines: List[Dict[str, Any]],
    sender_code: str = "YUNCE_BILLING_V2",
) -> str:
    detail_xml: List[str] = []
    for idx, ln in enumerate(lines, start=1):
        acct = str(ln.get("account_code") or "600101")
        dr_yuan = int(ln.get("debit_cents") or 0) / 100.0
        cr_yuan = int(ln.get("credit_cents") or 0) / 100.0
        cust_aux = str(ln.get("customer_aux_code") or "")
        abstract = str(ln.get("abstract") or "SaaS月度结算凭证")

        aux_block = ""
        if cust_aux:
            aux_block = (
                "          <ass>\n"
                "            <item>\n"
                "              <pk_Checktype>0001_CUST_AUX</pk_Checktype>\n"
                f"              <pk_Checkvalue>{cust_aux}</pk_Checkvalue>\n"
                "            </item>\n"
                "          </ass>\n"
            )

        detail_xml.append(
            f'        <item id="{idx}">\n'
            f'          <detailindex>{idx}</detailindex>\n'
            f'          <accsubjcode>{acct}</accsubjcode>\n'
            f'          <explanation>{abstract}</explanation>\n'
            f'          <debitamount>{dr_yuan:.2f}</debitamount>\n'
            f'          <creditamount>{cr_yuan:.2f}</creditamount>\n'
            + aux_block
            + '        </item>'
        )

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<ufinterface account="01" billtype="vouchergl" sender="{sender_code}" isexchange="Y">\n'
        f'  <voucher id="{voucher_id}">\n'
        '    <voucher_head>\n'
        '      <pk_vouchertype>记字</pk_vouchertype>\n'
        f'      <year>{accounting_year}</year>\n'
        f'      <period>{accounting_month}</period>\n'
        '      <pk_prepared>YUNCE_FIN_BOT</pk_prepared>\n'
        '    </voucher_head>\n'
        '    <voucher_body>\n'
        + "\n".join(detail_xml) + "\n"
        '    </voucher_body>\n'
        '  </voucher>\n'
        '</ufinterface>'
    )


def validate_ufinterface_gl_voucher_xml(xml_text: str) -> Dict[str, Any]:
    try:
        root = ET.fromstring((xml_text or "").strip())
    except ET.ParseError as exc:
        return {"valid": False, "errors": [f"XML_PARSE_ERROR:{exc}"], "debit_cents": 0, "credit_cents": 0}

    errors: List[str] = []
    dr_sum_cents = 0
    cr_sum_cents = 0
    item_count = 0

    for item in root.findall(".//voucher_body/item"):
        item_count += 1
        idx = item.findtext("detailindex", default=str(item_count))
        acct = (item.findtext("accsubjcode") or "").strip()
        dr_s = (item.findtext("debitamount") or "0.00").strip()
        cr_s = (item.findtext("creditamount") or "0.00").strip()

        dw, _, df = dr_s.partition(".")
        cw, _, cf = cr_s.partition(".")
        dr_c = int(dw or "0") * 100 + int((df + "00")[:2])
        cr_c = int(cw or "0") * 100 + int((cf + "00")[:2])
        dr_sum_cents += dr_c
        cr_sum_cents += cr_c

        if dr_c > 0 and cr_c > 0:
            errors.append(f"LINE_{idx}:BOTH_DEBIT_AND_CREDIT_NONZERO")
        if any(acct.startswith(pfx) for pfx in CUSTOMER_AUX_REQUIRED_PREFIXES):
            aux_val = item.findtext(".//ass/item/pk_Checkvalue", default="").strip()
            if not aux_val:
                errors.append(f"LINE_{idx}:MISSING_REQUIRED_CUSTOMER_AUX_FOR_{acct}")

    if item_count == 0:
        errors.append("EMPTY_VOUCHER_BODY")
    if dr_sum_cents != cr_sum_cents:
        errors.append(f"TRIAL_BALANCE_MISMATCH:DR={dr_sum_cents}!=CR={cr_sum_cents}")

    return {
        "valid": len(errors) == 0,
        "line_count": item_count,
        "debit_cents": dr_sum_cents,
        "credit_cents": cr_sum_cents,
        "errors": errors,
    }
