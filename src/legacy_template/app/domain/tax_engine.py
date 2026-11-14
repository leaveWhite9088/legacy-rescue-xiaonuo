# -*- coding: utf-8 -*-
"""多区域税率核算引擎（支持含税价内剥离与价外附加税）。"""
from typing import Any, Dict

from app.domain.money import apply_bps
from app.infra.config import TAX_PROFILES


def compute_tax_breakdown(subtotal_cents: int, tax_profile_code: str) -> Dict[str, Any]:
    """根据租户税务档案计算税额与应付总额。

    - 若 inclusive=True（默认 CN_VAT_6_INCLUSIVE）：标价已含税，应付总额 = subtotal_cents，
      内部剥离展示税额供总账入账参考；tax_added_cents = 0。
    - 若 inclusive=False（如 CN_VAT_6_EXCLUSIVE 专票价外税客户）：在净额之上加收税款，
      tax_added_cents = round(subtotal * rate_bps / 10000)，应付总额 = subtotal + tax_added_cents。
    """
    profile = TAX_PROFILES.get(tax_profile_code) or TAX_PROFILES["CN_VAT_6_INCLUSIVE"]
    rate_bps = int(profile["rate_bps"])
    inclusive = bool(profile["inclusive"])

    if subtotal_cents <= 0 or rate_bps <= 0:
        return {
            "tax_profile_code": profile["code"],
            "inclusive": inclusive,
            "rate_bps": rate_bps,
            "subtotal_cents": subtotal_cents,
            "tax_added_cents": 0,
            "embedded_tax_cents": 0,
            "gross_total_cents": subtotal_cents,
        }

    if inclusive:
        # 含税价剥离：tax = subtotal - subtotal / (1 + rate)
        net_est = (subtotal_cents * 10000 + (10000 + rate_bps) // 2) // (10000 + rate_bps)
        embedded = max(0, subtotal_cents - net_est)
        return {
            "tax_profile_code": profile["code"],
            "inclusive": True,
            "rate_bps": rate_bps,
            "subtotal_cents": subtotal_cents,
            "tax_added_cents": 0,
            "embedded_tax_cents": embedded,
            "gross_total_cents": subtotal_cents,
        }

    added_tax = apply_bps(subtotal_cents, rate_bps)
    return {
        "tax_profile_code": profile["code"],
        "inclusive": False,
        "rate_bps": rate_bps,
        "subtotal_cents": subtotal_cents,
        "tax_added_cents": added_tax,
        "embedded_tax_cents": 0,
        "gross_total_cents": subtotal_cents + added_tax,
    }
