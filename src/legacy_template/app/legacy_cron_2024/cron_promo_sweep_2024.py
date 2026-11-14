# -*- coding: utf-8 -*-
"""[ARCHIVED 2024 CRON] 2024 营销体验金月末清零旧脚本（已被 `app.domain.ledger.expire_promo_grants` 取代）。"""
from typing import Any, Dict, List


def preview_2024_voucher_expiry(vouchers: List[Dict[str, Any]], cutoff_ymd: str) -> Dict[str, Any]:
    expired_codes: List[str] = []
    total_reclaimed = 0
    for v in vouchers:
        if str(v.get("expires_ymd") or "9999-12-31") < cutoff_ymd and v.get("active", False):
            expired_codes.append(str(v.get("code")))
            total_reclaimed += max(0, int(v.get("unused_cents") or 0))
    return {"expired_codes": expired_codes, "reclaimed_cents": total_reclaimed, "archived_script": True}
