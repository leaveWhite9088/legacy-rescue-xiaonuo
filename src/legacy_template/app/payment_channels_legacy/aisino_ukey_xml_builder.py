# -*- coding: utf-8 -*-
"""航信税务 UKey KP_FPKJ 报文拼装遗留工具（供历史纸电混合票归档重放核验）。"""
from typing import Dict, List


def build_aisino_fpkj_xml(buyer_name: str, buyer_tax_no: str, items: List[Dict[str, object]]) -> str:
    total_net = 0
    total_tax = 0
    item_xml = []
    for idx, it in enumerate(items, start=1):
        nc = int(it.get("net_cents") or 0)
        tc = int(it.get("tax_cents") or 0)
        total_net += nc
        total_tax += tc
        item_xml.append(
            f"<FPKJXX_XMXX><XH>{idx}</XH><XMMC>{it.get('name', 'SaaS技术服务费')}</XMMC>"
            f"<XMJE>{nc / 100:.2f}</XMJE><SE>{tc / 100:.2f}</SE></FPKJXX_XMXX>"
        )
    return (
        f"<REQUEST_FPKJ><GHFMC>{buyer_name}</GHFMC><GHF_NSRSBH>{buyer_tax_no}</GHF_NSRSBH>"
        f"<HJJE>{total_net / 100:.2f}</HJJE><HJSE>{total_tax / 100:.2f}</HJSE>"
        f"{''.join(item_xml)}</REQUEST_FPKJ>"
    )
