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


def sync_red_letter_confirmations(
    conn: Any,
    confirmations: list,
    operator: str = "tax_sync_bot",
) -> Dict[str, Any]:
    """批量同步税局已确认红字发票回执入库。"""
    from app.infra.db import utc_now_iso
    from app.repos.fapiao_repo import get_fapiao_by_id, insert_fapiao_request
    import uuid

    synced = []
    skipped = 0
    now = utc_now_iso()
    for item in confirmations or []:
        orig_id = str((item or {}).get("original_fapiao_id") or "").strip()
        orig = get_fapiao_by_id(conn, orig_id) if orig_id else None
        if not orig:
            skipped += 1
            continue
        red_id = str(item.get("red_fapiao_id") or f"FP-RED-{uuid.uuid4().hex[:6].upper()}")
        # 登记红字确认回执记录（按原票面绝对值归档备查）
        red_record = {
            "id": red_id,
            "tenant_id": orig["tenant_id"],
            "invoice_id": orig["invoice_id"],
            "fapiao_type": orig["fapiao_type"],
            "buyer_tax_id": orig["buyer_tax_id"],
            "title": orig["title"],
            "net_amount_cents": abs(int(orig["net_amount_cents"])),
            "tax_amount_cents": abs(int(orig["tax_amount_cents"])),
            "gross_amount_cents": abs(int(orig["gross_amount_cents"])),
            "sheet_count": 1,
            "status": "RED_ISSUED",
            "red_letter_of": orig_id,
            "created_at": now,
        }
        insert_fapiao_request(conn, red_record)
        synced.append(red_record)

    return {
        "synced_count": len(synced),
        "skipped_count": skipped,
        "records": synced,
    }
