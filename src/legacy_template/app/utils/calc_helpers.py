# -*- coding: utf-8 -*-
"""历史遗留算术与统计辅助函数集（与 domain.money 部分重叠，供报表、风控、催收模块调用）。"""
import math
from typing import Dict, Iterable, List, Sequence, Tuple


def clamp_int(val: int, lo: int, hi: int) -> int:
    return max(int(lo), min(int(hi), int(val)))


def safe_div_bps(numerator: int, denominator: int) -> int:
    if int(denominator) == 0:
        return 0
    return int(round((float(numerator) / float(denominator)) * 10000.0))


def weighted_moving_average(values: Sequence[float], weights: Sequence[float] | None = None) -> float:
    if not values:
        return 0.0
    if weights is None:
        n = len(values)
        weights = [float(i + 1) for i in range(n)]
    w_sum = sum(weights)
    if w_sum <= 0:
        return 0.0
    return sum(float(v) * float(w) for v, w in zip(values, weights)) / w_sum


def compute_z_score(sample: float, history: Sequence[float]) -> float:
    if len(history) < 2:
        return 0.0
    mean = sum(history) / len(history)
    var = sum((x - mean) ** 2 for x in history) / (len(history) - 1)
    std = math.sqrt(max(var, 1e-9))
    return (float(sample) - mean) / std


def allocate_pro_rata_cents(total_cents: int, weights: Sequence[int]) -> List[int]:
    """最大余数法（Largest Remainder Method）按权重精确分摊金额，保证分摊总和恒等于 total_cents。"""
    if not weights:
        return []
    w_clean = [max(0, int(w)) for w in weights]
    w_sum = sum(w_clean)
    if w_sum == 0:
        base = int(total_cents) // len(w_clean)
        rem = int(total_cents) - base * len(w_clean)
        return [base + (1 if i < rem else 0) for i in range(len(w_clean))]

    raw_shares = [(int(total_cents) * w) / w_sum for w in w_clean]
    floors = [int(math.floor(x)) for x in raw_shares]
    rem = int(total_cents) - sum(floors)
    remainders: List[Tuple[float, int]] = sorted(
        [(raw_shares[i] - floors[i], i) for i in range(len(w_clean))],
        key=lambda t: (-t[0], t[1]),
    )
    for k in range(max(0, rem)):
        floors[remainders[k][1]] += 1
    return floors


def bucket_aging_days(overdue_days: int) -> str:
    if overdue_days <= 0:
        return "CURRENT"
    if overdue_days <= 30:
        return "DAYS_1_30"
    if overdue_days <= 60:
        return "DAYS_31_60"
    if overdue_days <= 90:
        return "DAYS_61_90"
    return "DAYS_90_PLUS"


def summarize_cent_distribution(amounts: Iterable[int]) -> Dict[str, int]:
    arr = sorted(int(x) for x in amounts)
    if not arr:
        return {"count": 0, "sum_cents": 0, "p50_cents": 0, "p90_cents": 0, "max_cents": 0}
    n = len(arr)
    p50 = arr[min(n - 1, n // 2)]
    p90 = arr[min(n - 1, int(n * 0.9))]
    return {
        "count": n,
        "sum_cents": sum(arr),
        "p50_cents": p50,
        "p90_cents": p90,
        "max_cents": arr[-1],
    }
