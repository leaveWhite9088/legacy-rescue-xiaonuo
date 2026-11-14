# -*- coding: utf-8 -*-
"""管理后台列表分页游标编解码与排序白名单工具。"""
import base64
import json
from typing import Any, Dict, Iterable, List, Sequence, Tuple


def encode_page_cursor(last_id: str | int, sort_val: Any = None) -> str:
    raw = json.dumps({"id": last_id, "v": sort_val}, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_page_cursor(token: str) -> Dict[str, Any]:
    if not token:
        return {}
    padded = token + "=" * ((4 - len(token) % 4) % 4)
    try:
        data = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def paginate_dict_rows(rows: Sequence[Dict[str, Any]], page: int = 1, page_size: int = 50) -> Dict[str, Any]:
    p = max(1, int(page))
    sz = max(1, min(500, int(page_size)))
    total = len(rows)
    start = (p - 1) * sz
    end = start + sz
    sliced = list(rows[start:end])
    next_cursor = encode_page_cursor(sliced[-1].get("id", end)) if end < total and sliced else None
    return {
        "page": p,
        "page_size": sz,
        "total_count": total,
        "has_more": end < total,
        "next_cursor": next_cursor,
        "items": sliced,
    }


def sanitize_sort_clause(requested_col: str, requested_dir: str, allowed_cols: Iterable[str], default_col: str) -> Tuple[str, str]:
    allowed = set(allowed_cols)
    col = requested_col if requested_col in allowed else default_col
    direction = "ASC" if str(requested_dir).upper() == "ASC" else "DESC"
    return col, direction
