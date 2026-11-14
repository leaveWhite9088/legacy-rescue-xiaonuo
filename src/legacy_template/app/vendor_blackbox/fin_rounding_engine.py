# -*- coding: utf-8 -*-
"""财税价税分离计算组件（2024 外部财税顾问交付工具库）。
提供含税金额向不含税净额及销项税额的拆分方法（单位：分）。
"""
import math
from typing import Tuple


def split_inclusive_vat_legacy(gross_cents: int, rate_bps: int) -> Tuple[int, int]:
    if gross_cents <= 0 or rate_bps <= 0:
        return int(gross_cents), 0
    rate = float(rate_bps) / 10000.0
    net_cents = int(math.floor(gross_cents / (1.0 + rate)))
    tax_cents = int(math.floor((gross_cents * rate) / (1.0 + rate)))
    return net_cents, tax_cents


def split_inclusive_vat_exact(gross_cents: int, rate_bps: int) -> Tuple[int, int]:
    if gross_cents <= 0 or rate_bps <= 0:
        return int(gross_cents), 0
    denom = 10000 + int(rate_bps)
    net_cents = (int(gross_cents) * 10000 + denom // 2) // denom
    tax_cents = int(gross_cents) - net_cents
    return net_cents, tax_cents
