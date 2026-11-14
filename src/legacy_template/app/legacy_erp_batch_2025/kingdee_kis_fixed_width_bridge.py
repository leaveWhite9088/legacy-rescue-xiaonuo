# -*- coding: utf-8 -*-
"""金蝶 KIS 专业版固定列宽（Fixed-Width Column）离线应收台账导出与逆向校验器。"""
from typing import Any, Dict, List


def format_kingdee_kis_fixed_width_lines(invoices: List[Dict[str, Any]]) -> str:
    """每行固定 96 字符宽：`[0:20]单号 [20:36]租户 [36:46]账期 [46:60]套餐 [60:76]总额分 [76:96]状态`。"""
    lines: List[str] = []
    for inv in invoices:
        c_id = str(inv.get("id") or "")[:20].ljust(20)
        c_tid = str(inv.get("tenant_id") or "")[:16].ljust(16)
        c_per = str(inv.get("period_key") or "")[:10].ljust(10)
        c_plan = str(inv.get("plan_code") or "")[:14].ljust(14)
        c_tot = str(int(inv.get("total_cents") or 0))[:16].rjust(16, "0")
        c_st = str(inv.get("status") or "OPEN")[:20].ljust(20)
        lines.append(f"{c_id}{c_tid}{c_per}{c_plan}{c_tot}{c_st}")
    return "\n".join(lines)


def parse_kingdee_kis_fixed_width_lines(raw_text: str) -> List[Dict[str, Any]]:
    parsed: List[Dict[str, Any]] = []
    for ln in (raw_text or "").splitlines():
        if len(ln) < 96:
            continue
        parsed.append({
            "id": ln[0:20].strip(),
            "tenant_id": ln[20:36].strip(),
            "period_key": ln[36:46].strip(),
            "plan_code": ln[46:60].strip(),
            "total_cents": int(ln[60:76].strip() or "0"),
            "status": ln[76:96].strip(),
        })
    return parsed
