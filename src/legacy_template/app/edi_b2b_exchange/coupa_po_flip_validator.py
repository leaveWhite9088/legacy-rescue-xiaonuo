# -*- coding: utf-8 -*-
"""Coupa 企业采购协同平台三单匹配（3-Way Match：采购订单 PO <-> 服务确认单 SES <-> 电子账单 Invoice）容差核验器。"""
from typing import Any, Dict, List


def validate_coupa_po_three_way_match(
    po_record: Dict[str, Any],
    service_entry_sheet: Dict[str, Any],
    invoice_draft: Dict[str, Any],
    price_tolerance_bps: int = 100,
) -> Dict[str, Any]:
    """检验开票金额是否超出客户采购订单剩余可用授信池或服务验收单上限。"""
    po_ceiling = max(0, int(po_record.get("authorized_total_cents") or 0))
    po_consumed = max(0, int(po_record.get("already_invoiced_cents") or 0))
    po_remaining = max(0, po_ceiling - po_consumed)

    ses_approved = max(0, int(service_entry_sheet.get("approved_service_cents") or 0))
    inv_total = max(0, int(invoice_draft.get("total_cents") or 0))
    allowed_with_tol = ses_approved + (ses_approved * max(0, int(price_tolerance_bps))) // 10000

    exceptions: List[str] = []
    if str(po_record.get("status") or "OPEN").upper() != "OPEN":
        exceptions.append(f"PO_NOT_OPEN:{po_record.get('status')}")
    if inv_total > po_remaining:
        exceptions.append(f"EXCEEDS_PO_REMAINING_BUDGET:{inv_total}>{po_remaining}")
    if ses_approved > 0 and inv_total > allowed_with_tol:
        exceptions.append(f"EXCEEDS_SES_TOLERANCE_CEILING:{inv_total}>{allowed_with_tol}")

    return {
        "po_number": po_record.get("po_number"),
        "matched": len(exceptions) == 0,
        "po_remaining_before_cents": po_remaining,
        "po_remaining_after_cents": max(0, po_remaining - inv_total) if not exceptions else po_remaining,
        "exceptions": exceptions,
    }
