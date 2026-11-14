# -*- coding: utf-8 -*-
"""企业客户自建 ERP 回调 Webhook 信封组装、HMAC-SHA256 防篡改签名与指数退避重试计划计算器。"""
import hashlib
import hmac
import json
from typing import Any, Dict, List


RETRY_BACKOFF_SECONDS = (0, 30, 180, 900, 3600, 14400)


def build_signed_webhook_envelope(
    event_type: str,
    tenant_id: str,
    payload: Dict[str, Any],
    signing_secret: str = "whsec_yunce_v2_default_key",
    delivery_attempt: int = 1,
) -> Dict[str, Any]:
    """构造带标准 `X-YunCe-Signature-256` 头部摘要的回调信封。"""
    canonical_body = json.dumps(
        {
            "schema_version": "2025-10-01",
            "event_type": event_type,
            "tenant_id": tenant_id,
            "attempt": max(1, int(delivery_attempt)),
            "data": payload,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hmac.new(
        signing_secret.encode("utf-8"),
        canonical_body.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    idx = min(len(RETRY_BACKOFF_SECONDS) - 1, max(0, int(delivery_attempt) - 1))
    return {
        "headers": {
            "Content-Type": "application/json; charset=utf-8",
            "X-YunCe-Event": event_type,
            "X-YunCe-Tenant": tenant_id,
            "X-YunCe-Signature-256": f"sha256={digest}",
        },
        "body_json": canonical_body,
        "next_retry_delay_seconds": RETRY_BACKOFF_SECONDS[idx],
    }


def verify_webhook_signature(canonical_body: str, header_sig: str, signing_secret: str) -> bool:
    expected = "sha256=" + hmac.new(
        signing_secret.encode("utf-8"),
        canonical_body.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, header_sig or "")
