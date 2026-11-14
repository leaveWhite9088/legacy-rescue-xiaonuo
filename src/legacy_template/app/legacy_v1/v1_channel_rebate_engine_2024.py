# -*- coding: utf-8 -*-
"""2024 区域总代与二级经销商多级返点、市场发展基金 (MDF) 及报备冲突仲裁模块 (LEGACY)。
注意：2025 年起线上渠道月结统一简化为 app.domain.partner_commission（单层净现金回款返佣）。
本模块保留 2024 老总代协议（含首年激励加成、MDF 计提、跨区撞单拆分）离线核对逻辑。
"""
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

V1_DISTRIBUTOR_CONTRACTS = {
    "DIST_EAST_HQ": {"region": "EAST", "base_rebate_bps": 1200, "mdf_accrual_bps": 200, "sub_override_bps": 300},
    "DIST_SOUTH_HQ": {"region": "SOUTH", "base_rebate_bps": 1000, "mdf_accrual_bps": 150, "sub_override_bps": 250},
    "DIST_NORTH_HQ": {"region": "NORTH", "base_rebate_bps": 1400, "mdf_accrual_bps": 250, "sub_override_bps": 300},
}


@dataclass(frozen=True)
class V1DealRegistration:
    reg_id: str
    partner_code: str
    distributor_code: Optional[str]
    tenant_id: str
    submitted_day_seq: int
    verified_poc_completed: bool
    incumbent_renewal: bool = False


def arbitrate_v1_deal_conflict(registrations: List[V1DealRegistration]) -> Dict[str, Any]:
    """2024 渠道商机撞单仲裁规则：
    1. 存量续费单优先归属原绑定合作伙伴；
    2. 新签商机若已完成技术 POC 验收者优先；
    3. 同等条件下按商机报备时间戳先后顺序（先报先得），次选方若协助陪标可获 20% 协作分润。
    """
    if not registrations:
        return {"winner": None, "co_sell_partner": None, "split_winner_bps": 0, "split_cosell_bps": 0}

    incumbents = [r for r in registrations if r.incumbent_renewal]
    if incumbents:
        chosen = sorted(incumbents, key=lambda x: x.submitted_day_seq)[0]
        return {
            "winner": chosen.partner_code,
            "registration_id": chosen.reg_id,
            "co_sell_partner": None,
            "split_winner_bps": 10000,
            "split_cosell_bps": 0,
            "rule": "INCUMBENT_RENEWAL_PROTECTION",
        }

    ordered = sorted(
        registrations,
        key=lambda r: (0 if r.verified_poc_completed else 1, r.submitted_day_seq, r.reg_id),
    )
    winner = ordered[0]
    runner_up = ordered[1] if len(ordered) > 1 and ordered[1].partner_code != winner.partner_code else None

    if runner_up and runner_up.verified_poc_completed:
        return {
            "winner": winner.partner_code,
            "registration_id": winner.reg_id,
            "co_sell_partner": runner_up.partner_code,
            "split_winner_bps": 8000,
            "split_cosell_bps": 2000,
            "rule": "DUAL_POC_COSELL_80_20",
        }

    return {
        "winner": winner.partner_code,
        "registration_id": winner.reg_id,
        "co_sell_partner": None,
        "split_winner_bps": 10000,
        "split_cosell_bps": 0,
        "rule": "FIRST_QUALIFIED_REGISTRATION",
    }


def compute_v1_two_tier_distributor_waterfall(
    distributor_code: str,
    deal_records: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """计算区域总代管理津贴、二级代理商直接返佣、赠送金剔除项及退费倒扣额。"""
    spec = V1_DISTRIBUTOR_CONTRACTS.get(distributor_code, V1_DISTRIBUTOR_CONTRACTS["DIST_EAST_HQ"])
    total_gross_receipts = 0
    total_promo_excluded = 0
    total_refund_clawbacks = 0
    net_commissionable = 0
    sub_partner_payout = 0
    distributor_override = 0
    mdf_accrued = 0

    breakdown: List[Dict[str, Any]] = []
    for rec in deal_records:
        gross = max(0, int(rec.get("gross_paid_cents") or 0))
        promo = max(0, int(rec.get("promo_paid_cents") or 0))
        refunded = max(0, int(rec.get("refunded_cents") or 0))
        cash_only = max(0, gross - promo)
        eligible = max(0, cash_only - refunded)

        has_sub = bool(rec.get("sub_partner_code"))
        if has_sub:
            sub_bps = int(rec.get("sub_partner_bps") or 800)
            sub_amt = (eligible * sub_bps) // 10000
            dist_amt = (eligible * int(spec["sub_override_bps"])) // 10000
        else:
            sub_amt = 0
            dist_amt = (eligible * int(spec["base_rebate_bps"])) // 10000

        mdf_amt = (eligible * int(spec["mdf_accrual_bps"])) // 10000

        total_gross_receipts += gross
        total_promo_excluded += promo
        total_refund_clawbacks += min(cash_only, refunded)
        net_commissionable += eligible
        sub_partner_payout += sub_amt
        distributor_override += dist_amt
        mdf_accrued += mdf_amt

        breakdown.append({
            "invoice_id": rec.get("invoice_id"),
            "eligible_cash_cents": eligible,
            "sub_partner_cents": sub_amt,
            "distributor_cents": dist_amt,
            "mdf_cents": mdf_amt,
        })

    return {
        "distributor_code": distributor_code,
        "region": spec["region"],
        "gross_receipts_cents": total_gross_receipts,
        "promo_excluded_cents": total_promo_excluded,
        "refund_clawback_cents": total_refund_clawbacks,
        "net_commissionable_cash_cents": net_commissionable,
        "sub_partner_payout_cents": sub_partner_payout,
        "distributor_payout_cents": distributor_override,
        "mdf_fund_accrual_cents": mdf_accrued,
        "breakdown": breakdown,
    }
