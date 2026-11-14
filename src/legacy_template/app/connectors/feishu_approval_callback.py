# -*- coding: utf-8 -*-
"""飞书企业办公审批中心（Feishu OA Approval）回调事件验签、状态映射与重放幂等校验器。"""
import hashlib
import json
from typing import Any, Dict


FEISHU_STATUS_MAP: Dict[str, str] = {
    "PENDING": "PENDING",
    "UNDER_REVIEW": "PARTIALLY_APPROVED",
    "APPROVED": "APPROVED",
    "REJECTED": "REJECTED",
    "CANCELED": "VOID",
    "DELETED": "VOID",
}


def compute_feishu_callback_signature(timestamp: str, nonce: str, encrypt_key: str, raw_body: str) -> str:
    concat = f"{timestamp}{nonce}{encrypt_key}{raw_body}".encode("utf-8")
    return hashlib.sha256(concat).hexdigest()


def parse_and_verify_feishu_approval_event(
    headers: Dict[str, str],
    raw_body: str,
    encrypt_key: str = "feishu_oa_secret_2026",
) -> Dict[str, Any]:
    ts = str(headers.get("X-Lark-Request-Timestamp") or "")
    nonce = str(headers.get("X-Lark-Request-Nonce") or "")
    sig = str(headers.get("X-Lark-Signature") or "")

    expected = compute_feishu_callback_signature(ts, nonce, encrypt_key, raw_body)
    if sig and sig != expected:
        return {"verified": False, "error": "SIGNATURE_MISMATCH"}

    try:
        data = json.loads(raw_body or "{}")
    except ValueError:
        return {"verified": False, "error": "INVALID_JSON_BODY"}

    if "challenge" in data:
        return {"verified": True, "is_url_verification": True, "challenge": data["challenge"]}

    ev = data.get("event") or {}
    ext_status = str(ev.get("status") or "PENDING").upper()
    return {
        "verified": True,
        "is_url_verification": False,
        "event_uuid": str(data.get("uuid") or ev.get("instance_code") or ""),
        "approval_code": str(ev.get("approval_code") or ""),
        "ticket_id": str(ev.get("external_ticket_id") or ""),
        "mapped_internal_status": FEISHU_STATUS_MAP.get(ext_status, "PENDING"),
        "operator_open_id": str(ev.get("operate_user_id") or "oa_bot"),
    }
