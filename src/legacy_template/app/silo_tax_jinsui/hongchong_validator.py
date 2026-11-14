# -*- coding: utf-8 -*-
"""红字信息表（红冲申请单）跨月税局规则校验器。"""
from typing import Any, Dict


RED_REASON_CODES = {
    "01": "开票有误",
    "02": "销货退回",
    "03": "服务中止",
    "04": "销售折让",
}


def validate_hongchong_request(
    blue_fapiao: Dict[str, Any],
    requested_red_cents: int,
    reason_code: str = "04",
    buyer_deducted_vat: bool = False,
) -> Dict[str, Any]:
    gross_blue = abs(int(blue_fapiao.get("gross_amount_cents") or 0))
    req = abs(int(requested_red_cents))
    errors = []

    if reason_code not in RED_REASON_CODES:
        errors.append(f"未知红冲原因代码: {reason_code}")
    if req <= 0 or req > gross_blue:
        errors.append(f"红冲含税金额 {req} 超出原蓝票上限 {gross_blue}")
    if blue_fapiao.get("status") == "RED_REVERSED":
        errors.append("原蓝字数电票已全额红冲，禁止二次冲红")

    initiator = "BUYER_CONFIRM_REQUIRED" if buyer_deducted_vat else "SELLER_DIRECT_ISSUE"
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "workflow_mode": initiator,
        "reason_desc": RED_REASON_CODES.get(reason_code, ""),
    }
