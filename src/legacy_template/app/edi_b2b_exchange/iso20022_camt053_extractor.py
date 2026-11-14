# -*- coding: utf-8 -*-
"""ISO 20022 `camt.053.001.08` XML 银行日终客户账户对账单提取器（面向欧资与跨国银行银企直联通道）。"""
import xml.etree.ElementTree as ET
from typing import Any, Dict, List


def extract_camt053_entries(xml_text: str) -> Dict[str, Any]:
    """解析无命名空间或标准 ISO 20022 命名空间的 `BkToCstmrStmt` 节点，提取贷方收款条目。"""
    if not (xml_text or "").strip():
        return {"statement_id": "", "entries": [], "total_credit_cents": 0}

    root = ET.fromstring(xml_text.strip())
    # 剥离 XML namespace 前缀以便统一检索标签
    for elem in root.iter():
        if "}" in elem.tag:
            elem.tag = elem.tag.split("}", 1)[1]

    stmt = root.find(".//Stmt")
    if stmt is None:
        return {"statement_id": "", "entries": [], "total_credit_cents": 0}

    stmt_id = stmt.findtext("Id", default="")
    entries: List[Dict[str, Any]] = []
    total_cr_cents = 0

    for ntry in stmt.findall("Ntry"):
        amt_txt = (ntry.findtext("Amt") or "0").strip()
        amt_el = ntry.find("Amt")
        ccy = amt_el.attrib.get("Ccy", "CNY") if amt_el is not None else "CNY"
        cdt_dbt = (ntry.findtext("CdtDbtInd") or "CRDT").strip().upper()
        end_to_end = ntry.findtext(".//EndToEndId", default="")
        ustrd_memo = ntry.findtext(".//Ustrd", default="")

        if "." in amt_txt:
            w, f = amt_txt.split(".", 1)
            cents = int(w or "0") * 100 + int((f + "00")[:2])
        else:
            cents = int(amt_txt or "0") * 100

        if cdt_dbt == "CRDT":
            total_cr_cents += cents
        entries.append({
            "currency": ccy,
            "direction": cdt_dbt,
            "amount_cents": cents,
            "end_to_end_id": end_to_end,
            "remittance_info": ustrd_memo,
        })

    return {
        "statement_id": stmt_id,
        "entries": entries,
        "total_credit_cents": total_cr_cents,
    }
