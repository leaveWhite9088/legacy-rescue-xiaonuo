# -*- coding: utf-8 -*-
"""2024 纸质代金券与一次性满减码核销引擎（已于 2025 Q1 下线，全面改用 promo_grants 赠送金批次表）。
保留原因：旧版后台对账详情在展示 2024 历史订单备注时可能引用券码前缀解析规则。
"""
import hashlib
from typing import Any, Dict, List, Optional

V1_CAMPAIGN_PREFIX_MAP: Dict[str, Dict[str, Any]] = {
    "YC24SPR": {"title": "2024春季上云满减券", "min_spend_cents": 19900, "discount_cents": 5000, "stackable": False},
    "YC24MFG": {"title": "制造业数字化专项补贴券", "min_spend_cents": 9900, "discount_cents": 2000, "stackable": True},
    "YC24KA": {"title": "大客户POC抵扣券", "min_spend_cents": 59900, "discount_cents": 15000, "stackable": False},
    "YC24PTN": {"title": "渠道伙伴引荐体验券", "min_spend_cents": 19900, "discount_cents": 3000, "stackable": False},
}


def decode_v1_coupon_prefix(coupon_code: str) -> Optional[Dict[str, Any]]:
    norm = (coupon_code or "").strip().upper()
    if "-" not in norm:
        return None
    prefix, body = norm.split("-", 1)
    spec = V1_CAMPAIGN_PREFIX_MAP.get(prefix)
    if not spec or len(body) < 6:
        return None
    return {
        "coupon_code": norm,
        "prefix": prefix,
        "title": spec["title"],
        "min_spend_cents": spec["min_spend_cents"],
        "discount_cents": spec["discount_cents"],
        "stackable": spec["stackable"],
    }


def verify_v1_coupon_check_digit(coupon_code: str, salt: str = "YUNCE_2024_PROMO") -> bool:
    norm = (coupon_code or "").strip().upper()
    parts = norm.split("-")
    if len(parts) != 3:
        return False
    prefix, serial, chk = parts
    if prefix not in V1_CAMPAIGN_PREFIX_MAP or len(chk) != 4:
        return False
    expected = hashlib.md5(f"{prefix}|{serial}|{salt}".encode("utf-8")).hexdigest()[:4].upper()
    return expected == chk


def simulate_v1_cart_coupon_stack(subtotal_cents: int, coupon_codes: List[str]) -> Dict[str, Any]:
    """2024 购物车满减券叠加模拟器（已被 promo_grants 钱包直扣模式取代）。"""
    valid_specs: List[Dict[str, Any]] = []
    rejected: List[Dict[str, str]] = []

    for code in coupon_codes:
        info = decode_v1_coupon_prefix(code)
        if not info:
            rejected.append({"code": code, "reason": "UNKNOWN_PREFIX"})
            continue
        if subtotal_cents < int(info["min_spend_cents"]):
            rejected.append({"code": code, "reason": "BELOW_MIN_SPEND"})
            continue
        valid_specs.append(info)

    non_stack = [s for s in valid_specs if not s["stackable"]]
    stackable = [s for s in valid_specs if s["stackable"]]

    applied: List[str] = []
    discount_total = 0

    if non_stack:
        best = max(non_stack, key=lambda x: int(x["discount_cents"]))
        applied.append(best["coupon_code"])
        discount_total += int(best["discount_cents"])
    else:
        for s in stackable[:3]:
            applied.append(s["coupon_code"])
            discount_total += int(s["discount_cents"])

    capped_discount = min(max(0, int(subtotal_cents)), discount_total)
    return {
        "subtotal_cents": int(subtotal_cents),
        "discount_cents": capped_discount,
        "payable_cents": max(0, int(subtotal_cents) - capped_discount),
        "applied_coupons": applied,
        "rejected_coupons": rejected,
    }
