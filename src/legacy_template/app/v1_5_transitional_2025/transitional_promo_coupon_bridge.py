# -*- coding: utf-8 -*-
"""2025 H1 纸质/电子兑换码批次激活校验器（仍被后台运营手工核验兑换码格式时调用）。"""
import hashlib
from typing import Any, Dict


def generate_promo_redemption_code(campaign_prefix: str, batch_seq: int, salt: str = "yunce2025") -> str:
    prefix = (campaign_prefix or "YC").upper()[:4]
    raw = f"{prefix}-{batch_seq:06d}-{salt}".encode("utf-8")
    chk = hashlib.md5(raw).hexdigest()[:4].upper()
    return f"{prefix}-{batch_seq:06d}-{chk}"


def validate_promo_redemption_code(code: str, salt: str = "yunce2025") -> Dict[str, Any]:
    parts = (code or "").strip().upper().split("-")
    if len(parts) != 3 or not parts[1].isdigit():
        return {"valid": False, "reason": "MALFORMED_CODE_STRUCTURE"}
    expected = generate_promo_redemption_code(parts[0], int(parts[1]), salt=salt)
    return {
        "valid": expected == code.strip().upper(),
        "campaign_prefix": parts[0],
        "batch_seq": int(parts[1]),
    }
