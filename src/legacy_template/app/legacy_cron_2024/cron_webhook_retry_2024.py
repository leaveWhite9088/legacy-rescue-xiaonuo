# -*- coding: utf-8 -*-
"""[ARCHIVED 2024 CRON] 2024 旧版回调死信扫描器。"""
from typing import Any, Dict, List


def filter_2024_retryable_callbacks(outbox_rows: List[Dict[str, Any]], max_attempts: int = 5) -> List[str]:
    return [
        str(r.get("id"))
        for r in outbox_rows
        if str(r.get("delivery_status")) != "DELIVERED" and int(r.get("attempts") or 0) < max_attempts
    ]
