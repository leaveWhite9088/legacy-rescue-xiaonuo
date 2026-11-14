# -*- coding: utf-8 -*-
"""百旺金赋 / 航信诺诺数电票税控报文组装器与纳税人识别号校验器。"""
import re
from typing import Any, Dict, List

from app.legacy_v1.v1_tax_table_2023 import lookup_golden_tax_spbm

_USCC_REGEX = re.compile(r"^[0-9A-HJ-NPQRTUWXY]{2}\d{6}[0-9A-HJ-NPQRTUWXY]{10}$")
_OLD_TAX_ID_REGEX = re.compile(r"^[A-Z0-9]{15}$|^[A-Z0-9]{20}$")


def validate_prc_buyer_tax_id(tax_id: str) -> bool:
    s = (tax_id or "").strip().upper()
    return bool(_USCC_REGEX.match(s) or _OLD_TAX_ID_REGEX.match(s))


def build_baiwang_einvoice_envelope(
    fapiao_id: str,
    seller_tax_id: str,
    buyer_tax_id: str,
    buyer_title: str,
    net_cents: int,
    tax_cents: int,
    fapiao_type: str = "VAT_SPECIAL_E",
    red_notice_no: str | None = None,
) -> Dict[str, Any]:
    spbm_info = lookup_golden_tax_spbm("SAAS_SUBSCRIPTION", is_export_exempt=(tax_cents == 0))
    is_red = int(net_cents) < 0
    invoice_kind_code = "02" if fapiao_type == "VAT_SPECIAL_E" else "01"
    lines: List[Dict[str, Any]] = [
        {
            "line_no": 1,
            "goods_code": spbm_info["spbm"],
            "goods_name": spbm_info["item_name"],
            "net_yuan": f"{int(net_cents) / 100.0:.2f}",
            "tax_rate": f"{spbm_info['default_vat_bps'] / 10000.0:.2f}",
            "tax_yuan": f"{int(tax_cents) / 100.0:.2f}",
            "line_nature": "1" if is_red else "0",
        }
    ]
    return {
        "interface_version": "BW_EINV_4.2",
        "serial_no": fapiao_id,
        "invoice_kind_code": invoice_kind_code,
        "billing_type": "2" if is_red else "1",
        "red_confirmation_uuid": red_notice_no,
        "seller": {"tax_id": seller_tax_id, "name": "云策企服网络科技（上海）有限公司"},
        "buyer": {"tax_id": buyer_tax_id, "name": buyer_title},
        "totals": {
            "net_cents": int(net_cents),
            "tax_cents": int(tax_cents),
            "gross_cents": int(net_cents) + int(tax_cents),
        },
        "items": lines,
    }
