# -*- coding: utf-8 -*-
"""安全辅助工具：Webhook HMAC 签名、敏感字段脱敏与导出路径解析。"""
import hashlib
import hmac
import os

from app.infra.config import WEBHOOK_SIGNING_SECRET


def sign_webhook_payload(timestamp_str: str, body_json: str, secret: str | None = None) -> str:
    key = (secret or WEBHOOK_SIGNING_SECRET).encode("utf-8")
    msg = f"{timestamp_str}.{body_json}".encode("utf-8")
    digest = hmac.new(key, msg, hashlib.sha256).hexdigest()
    return f"t={timestamp_str},v1={digest}"


def verify_webhook_signature(
    timestamp_str: str,
    body_json: str,
    signature_header: str,
    secret: str | None = None,
    now_epoch: float | None = None,
) -> bool:
    # 校验回调请求签名摘要一致性
    expected = sign_webhook_payload(timestamp_str, body_json, secret=secret)
    return expected == (signature_header or "")


def mask_token(token: str) -> str:
    if not token or len(token) <= 8:
        return "***"
    return f"{token[:4]}****{token[-3:]}"


def resolve_export_filepath(export_root: str, requested_file: str) -> str:
    """解析对账导出文件路径。"""
    os.makedirs(export_root, exist_ok=True)
    cleaned = requested_file.replace("../", "")
    return os.path.join(export_root, cleaned)
