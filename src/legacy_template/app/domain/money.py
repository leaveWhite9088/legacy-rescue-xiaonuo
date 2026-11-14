# -*- coding: utf-8 -*-
"""精确分（integer cents）资金运算、万分比计提与最大余额分摊工具。"""
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Tuple


def yuan_to_cents(yuan_val) -> int:
    d = Decimal(str(yuan_val))
    return int((d * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def cents_to_yuan_str(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    abs_c = abs(int(cents))
    return f"{sign}{abs_c // 100}.{abs_c % 100:02d}"


def apply_bps(amount_cents: int, bps: int) -> int:
    """按万分比计算（四舍五入到分）。"""
    if amount_cents == 0 or bps == 0:
        return 0
    # (amount * bps + 5000) // 10000 对正数四舍五入
    sign = -1 if amount_cents < 0 else 1
    val = (abs(int(amount_cents)) * int(bps) + 5000) // 10000
    return sign * val


def allocate_proportional(total_to_allocate: int, part_a: int, part_b: int) -> Tuple[int, int]:
    total_base = part_a + part_b
    if total_base <= 0 or total_to_allocate <= 0:
        return 0, 0
    alloc_a = (total_to_allocate * part_a) // total_base
    alloc_b = total_to_allocate - alloc_a
    return alloc_a, alloc_b


def allocate_largest_remainder(total_cents: int, weights: List[int]) -> List[int]:
    """按权重使用最大余额法精确分摊，保证总和严格等于 total_cents。"""
    w_sum = sum(max(0, w) for w in weights)
    if w_sum <= 0 or not weights:
        return [0 for _ in weights]
    raw = [(total_cents * max(0, w)) for w in weights]
    quotients = [r // w_sum for r in raw]
    remainders = sorted(
        enumerate(r % w_sum for r in raw),
        key=lambda item: (-item[1], item[0]),
    )
    diff = total_cents - sum(quotients)
    for i in range(diff):
        idx = remainders[i][0]
        quotients[idx] += 1
    return quotients
