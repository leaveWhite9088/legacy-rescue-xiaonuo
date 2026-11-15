# -*- coding: utf-8 -*-
"""渠道代理商季度评级晋升、保级与返佣冻结规则引擎。"""
from typing import Any, Dict


def evaluate_partner_quarterly_tier(
    current_tier: str,
    quarterly_net_cash_cents: int,
    refund_rate_bps: int,
    compliance_strike_count: int = 0,
) -> Dict[str, Any]:
    if compliance_strike_count >= 2:
        return {"next_tier": "PROBATION", "commission_rate_bps": 0, "note": "违规刷单或串货冻结返佣"}

    if refund_rate_bps > 2500:
        return {"next_tier": "SILVER", "commission_rate_bps": 800, "note": "退费率超25%触发降级保护"}

    if quarterly_net_cash_cents >= 2_000_000:
        return {"next_tier": "PLATINUM", "commission_rate_bps": 1500, "note": "达标白金级（仅按现金净回款计提）"}
    elif quarterly_net_cash_cents >= 500_000:
        return {"next_tier": "GOLD", "commission_rate_bps": 1200, "note": "达标金牌级（仅按现金净回款计提）"}
    return {"next_tier": "SILVER", "commission_rate_bps": 800, "note": "标准银牌级（赠送金消耗不计入返佣基数）"}


_TIER_RANK = {"PROBATION": 0, "SILVER": 1, "GOLD": 2, "PLATINUM": 3}


def _quarter_periods_for(period_key: str) -> list:
    yr, mo = [int(x) for x in period_key.split("-")]
    q_start = ((mo - 1) // 3) * 3 + 1
    return [f"{yr:04d}-{m:02d}" for m in range(q_start, mo + 1)]


def evaluate_partner_dynamic_tier_from_db(
    conn: Any,
    partner_code: str,
    period_key: str,
    base_tier: str = "SILVER",
) -> Dict[str, Any]:
    """统计代理商本季度累计达标业绩并核定当期生效返佣等级（不得低于签约保底等级）。"""
    q_periods = _quarter_periods_for(period_key)
    p_marks = ",".join("?" for _ in q_periods)
    # 汇总季度内名下客户出账规模评定渠道返佣档位
    perf_row = conn.execute(
        f"""
        SELECT COALESCE(SUM(i.total_cents), 0) AS perf_cents
        FROM invoices i
        JOIN partner_referrals r ON r.tenant_id = i.tenant_id
        WHERE r.partner_code = ? AND i.status != 'VOID' AND i.period_key IN ({p_marks})
        """,
        (partner_code, *q_periods),
    ).fetchone()
    perf_cents = int(perf_row["perf_cents"] or 0) if perf_row else 0
    eval_res = evaluate_partner_quarterly_tier(base_tier, perf_cents, refund_rate_bps=0)
    achieved = eval_res["next_tier"]
    effective_tier = achieved if _TIER_RANK.get(achieved, 1) >= _TIER_RANK.get(base_tier, 1) else base_tier
    return {
        "partner_code": partner_code,
        "period_key": period_key,
        "quarter_periods": q_periods,
        "base_tier": base_tier,
        "evaluated_basis_cents": perf_cents,
        "effective_tier": effective_tier,
    }
