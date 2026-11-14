# -*- coding: utf-8 -*-
"""中国工商银行银企互联（ICBC H2H）管道符定界批量回单对账文件（`.b2e`）解析与生成适配器。"""
from typing import Any, Dict, List


def parse_icbc_b2e_pipe_batch(raw_text: str) -> Dict[str, Any]:
    """解析工行对公回单批文件：首行为 `HDR|账号|日期|总笔数|总分值`，后续为 `DTL|流水号|借贷|分值|对方户名|摘要`。"""
    lines = [ln.strip() for ln in (raw_text or "").splitlines() if ln.strip()]
    if not lines or not lines[0].startswith("HDR|"):
        return {"valid_header": False, "control_matched": False, "details": []}

    hdr_parts = lines[0].split("|")
    declared_cnt = int(hdr_parts[3]) if len(hdr_parts) > 3 and hdr_parts[3].isdigit() else 0
    declared_cents = int(hdr_parts[4]) if len(hdr_parts) > 4 and hdr_parts[4].isdigit() else 0

    details: List[Dict[str, Any]] = []
    sum_cents = 0
    for ln in lines[1:]:
        if not ln.startswith("DTL|"):
            continue
        cols = ln.split("|")
        if len(cols) < 6:
            continue
        cents = int(cols[3]) if cols[3].isdigit() else 0
        sum_cents += cents
        details.append({
            "serial_no": cols[1],
            "dc_flag": cols[2],
            "amount_cents": cents,
            "counterparty": cols[4],
            "memo": cols[5],
        })

    return {
        "valid_header": True,
        "account_no": hdr_parts[1] if len(hdr_parts) > 1 else "",
        "batch_date": hdr_parts[2] if len(hdr_parts) > 2 else "",
        "declared_count": declared_cnt,
        "parsed_count": len(details),
        "declared_cents": declared_cents,
        "parsed_cents": sum_cents,
        "control_matched": len(details) == declared_cnt and sum_cents == declared_cents,
        "details": details,
    }
