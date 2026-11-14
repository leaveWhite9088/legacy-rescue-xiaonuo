# -*- coding: utf-8 -*-
"""合规审计日志字段级变更比对（Before/After Diff）与敏感隐私字段自动脱敏序列化器。"""
import json
from typing import Any, Dict, Iterable


SENSITIVE_FIELD_KEYWORDS = ("secret", "password", "token", "api_key", "card_no", "bank_account", "tax_id")


def mask_sensitive_value(field_name: str, val: Any) -> Any:
    if val is None:
        return None
    low = (field_name or "").lower()
    if any(k in low for k in SENSITIVE_FIELD_KEYWORDS):
        s = str(val)
        if len(s) <= 6:
            return "***"
        return f"{s[:3]}****{s[-3:]}"
    return val


def compute_sanitized_entity_diff(
    before: Dict[str, Any],
    after: Dict[str, Any],
    ignored_fields: Iterable[str] = ("updated_at",),
) -> Dict[str, Dict[str, Any]]:
    ignored = set(ignored_fields)
    all_keys = sorted(set(before.keys()) | set(after.keys()))
    changes: Dict[str, Dict[str, Any]] = {}

    for k in all_keys:
        if k in ignored:
            continue
        b_val = before.get(k)
        a_val = after.get(k)
        if b_val != a_val:
            changes[k] = {
                "before": mask_sensitive_value(k, b_val),
                "after": mask_sensitive_value(k, a_val),
            }
    return changes


def serialize_audit_diff_json(before: Dict[str, Any], after: Dict[str, Any]) -> str:
    diff = compute_sanitized_entity_diff(before, after)
    return json.dumps(diff, ensure_ascii=False, sort_keys=True)
