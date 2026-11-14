# -*- coding: utf-8 -*-
"""数电红字发票确认单（Red-Letter Confirmation Form）16 位信息表编号格式校验与原蓝票冲红上限比对器。"""
from typing import Any, Dict


def validate_red_letter_confirmation_request(
    info_sheet_no: str,
    original_blue_fapiao_cents: int,
    already_red_reversed_cents: int,
    requested_red_cents: int,
) -> Dict[str, Any]:
    clean_no = (info_sheet_no or "").strip()
    valid_no = len(clean_no) == 16 and clean_no.isdigit()

    blue = max(0, int(original_blue_fapiao_cents))
    already = max(0, int(already_red_reversed_cents))
    req = abs(int(requested_red_cents))
    remaining_reversible = max(0, blue - already)

    errors = []
    if not valid_no:
        errors.append("INVALID_16DIGIT_RED_INFO_SHEET_NO")
    if req <= 0:
        errors.append("ZERO_RED_REVERSAL_AMOUNT")
    if req > remaining_reversible:
        errors.append(f"EXCEEDS_REVERSIBLE_BLUE_BALANCE:{remaining_reversible}")

    return {
        "approved": len(errors) == 0,
        "info_sheet_no": clean_no,
        "requested_red_cents": -req,
        "remaining_blue_after_reversal_cents": max(0, remaining_reversible - req) if not errors else remaining_reversible,
        "errors": errors,
    }
