# -*- coding: utf-8 -*-
"""边缘网关租户突发 QPS 令牌桶与预付费余额熔断策略推演器。"""
from typing import Any, Dict, List


PLAN_RATE_LIMIT_PROFILES: Dict[str, Dict[str, int]] = {
    "LEGACY_FLAT_99": {"sustained_rps": 25, "burst_capacity": 60, "daily_hard_cap": 200_000},
    "STARTER": {"sustained_rps": 30, "burst_capacity": 80, "daily_hard_cap": 300_000},
    "PRO": {"sustained_rps": 150, "burst_capacity": 400, "daily_hard_cap": 2_000_000},
    "ENTERPRISE": {"sustained_rps": 800, "burst_capacity": 2_500, "daily_hard_cap": 25_000_000},
}


def simulate_token_bucket_traffic_burst(
    plan_code: str,
    per_second_arrivals: List[int],
    wallet_total_cents: int = 50_000,
    has_enterprise_credit_line: bool = False,
) -> Dict[str, Any]:
    """模拟连续 N 秒的客户端请求洪峰通过网关令牌桶后的放行量与 429 限流丢弃量。"""
    profile = PLAN_RATE_LIMIT_PROFILES.get(plan_code, PLAN_RATE_LIMIT_PROFILES["STARTER"])
    rate = int(profile["sustained_rps"])
    cap = int(profile["burst_capacity"])

    if wallet_total_cents <= 0 and not has_enterprise_credit_line:
        total_req = sum(max(0, int(x)) for x in per_second_arrivals)
        return {
            "circuit_breaker": "OPEN_INSUFFICIENT_PREPAID_FUNDS",
            "admitted_requests": 0,
            "throttled_429_requests": total_req,
            "ending_tokens": 0,
        }

    tokens = float(cap)
    admitted = 0
    throttled = 0

    for req_cnt in per_second_arrivals:
        incoming = max(0, int(req_cnt))
        if incoming <= tokens:
            admitted += incoming
            tokens -= incoming
        else:
            take = int(tokens)
            admitted += take
            throttled += incoming - take
            tokens = 0.0
        tokens = min(float(cap), tokens + float(rate))

    return {
        "circuit_breaker": "CLOSED_NORMAL",
        "plan_code": plan_code,
        "sustained_rps": rate,
        "burst_capacity": cap,
        "admitted_requests": admitted,
        "throttled_429_requests": throttled,
        "ending_tokens": int(tokens),
    }
