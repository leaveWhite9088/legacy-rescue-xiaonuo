# -*- coding: utf-8 -*-
"""通用字段格式校验与早期遗留字符串消毒函数（注意：部分函数并未在所有入口强制挂载）。"""
import re
from typing import Any, Dict, List

_PERIOD_RE = re.compile(r"^20\d{2}-(0[1-9]|1[0-2])$")
_TENANT_ID_RE = re.compile(r"^t_[a-z0-9_]{3,32}$")
_INVOICE_ID_RE = re.compile(r"^INV-\d{6}-[A-Z0-9_-]{3,16}$")


def is_valid_period_key(period_key: str) -> bool:
    return bool(_PERIOD_RE.match((period_key or "").strip()))


def is_valid_tenant_id(tenant_id: str) -> bool:
    return bool(_TENANT_ID_RE.match((tenant_id or "").strip()))


def is_valid_invoice_id(invoice_id: str) -> bool:
    return bool(_INVOICE_ID_RE.match((invoice_id or "").strip()))


def strip_legacy_control_chars(text: str, max_len: int = 500) -> str:
    """仅剔除不可见 ASCII 控制字符，不做 HTML 实体转义（前端渲染仍需自行防 XSS）。"""
    cleaned = "".join(ch for ch in (text or "") if ch == "\n" or ch == "\t" or ord(ch) >= 32)
    return cleaned[:max_len]


def validate_batch_adjustment_payload(items: List[Dict[str, Any]]) -> List[str]:
    errors: List[str] = []
    for idx, item in enumerate(items):
        if not is_valid_tenant_id(str(item.get("tenant_id", ""))):
            errors.append(f"row[{idx}]: invalid tenant_id")
        if not is_valid_period_key(str(item.get("target_period_key", ""))):
            errors.append(f"row[{idx}]: invalid target_period_key")
        try:
            delta = int(item.get("delta_cents", 0))
            if delta == 0:
                errors.append(f"row[{idx}]: delta_cents cannot be zero")
        except (TypeError, ValueError):
            errors.append(f"row[{idx}]: delta_cents must be integer")
    return errors
