# -*- coding: utf-8 -*-
"""大客户商务交易台 (Deal Desk CPQ v2)：套餐选型比价、多期付款计划、续约涨幅封顶与销售提成拆算引擎。"""
from dataclasses import dataclass
import math
from typing import Any, Dict, List, Optional

from app.domain.pricing import compute_tiered_overage_cents
from app.domain.tax_engine import compute_tax_breakdown
from app.infra.config import PLANS, TAX_PROFILES


@dataclass(frozen=True)
class DealSimulationInput:
    tenant_name: str
    projected_monthly_calls: int
    contract_months: int = 12
    tax_profile_code: str = "CN_VAT_6_INCLUSIVE"
    requested_overage_discount_bps: int = 0
    proposed_min_commit_cents: int = 0
    renewal_cap_bps: int = 700  # 续约价格年涨幅上限默认 7%
    billing_cadence: str = "MONTHLY"  # MONTHLY | QUARTERLY | ANNUAL


def compare_standard_plans_for_workload(
    projected_monthly_calls: int,
    tax_profile_code: str = "CN_VAT_6_INCLUSIVE",
) -> Dict[str, Any]:
    """针对预测月调用量，横向对比 STARTER / PRO / ENTERPRISE 三档标准套餐的税前与含税总成本。"""
    qty = max(0, int(projected_monthly_calls))
    candidates: List[Dict[str, Any]] = []

    for code in ("STARTER", "PRO", "ENTERPRISE"):
        spec = PLANS[code]
        base_c = int(spec["monthly_fee_cents"])
        inc_q = int(spec["included_quota"])
        ov_c = compute_tiered_overage_cents(qty, inc_q, spec["overage_tiers"])
        subtotal = base_c + ov_c
        tax_info = compute_tax_breakdown(subtotal, tax_profile_code)
        eff_unit_milli_cents = round((tax_info["gross_total_cents"] * 1000.0) / max(1, qty), 2)

        candidates.append({
            "plan_code": code,
            "plan_name": spec["name"],
            "included_quota": inc_q,
            "projected_overage_units": max(0, qty - inc_q),
            "base_fee_cents": base_c,
            "overage_fee_cents": ov_c,
            "tax_added_cents": tax_info["tax_added_cents"],
            "monthly_gross_cents": tax_info["gross_total_cents"],
            "annualized_gross_cents": tax_info["gross_total_cents"] * 12,
            "effective_milli_cents_per_call": eff_unit_milli_cents,
        })

    ordered = sorted(candidates, key=lambda x: (x["monthly_gross_cents"], x["plan_code"]))
    optimal = ordered[0]
    highest = ordered[-1]
    return {
        "projected_monthly_calls": qty,
        "tax_profile_code": tax_profile_code,
        "recommended_plan_code": optimal["plan_code"],
        "monthly_savings_vs_worst_cents": highest["monthly_gross_cents"] - optimal["monthly_gross_cents"],
        "candidates": candidates,
    }


def simulate_enterprise_custom_deal(sim: DealSimulationInput) -> Dict[str, Any]:
    """模拟签有最低月度保底消费与超额协议折扣的定制化框架合同现金流与审批路径。"""
    months = max(1, min(60, int(sim.contract_months)))
    disc_bps = max(0, min(4000, int(sim.requested_overage_discount_bps)))
    tp = TAX_PROFILES.get(sim.tax_profile_code, TAX_PROFILES["CN_VAT_6_INCLUSIVE"])

    ent = PLANS["ENTERPRISE"]
    base_c = int(ent["monthly_fee_cents"])
    raw_ov = compute_tiered_overage_cents(sim.projected_monthly_calls, int(ent["included_quota"]), ent["overage_tiers"])
    disc_ov = max(0, raw_ov - (raw_ov * disc_bps) // 10000)

    raw_monthly = base_c + disc_ov
    min_commit = max(0, int(sim.proposed_min_commit_cents))
    commit_topup = max(0, min_commit - raw_monthly)
    net_monthly = raw_monthly + commit_topup

    tax_res = compute_tax_breakdown(net_monthly, tp["code"])
    gross_monthly = int(tax_res["gross_total_cents"])
    total_contract_value_cents = gross_monthly * months

    cadence = sim.billing_cadence.upper()
    step_months = 12 if cadence == "ANNUAL" else (3 if cadence == "QUARTERLY" else 1)
    num_installments = int(math.ceil(months / float(step_months)))

    installments: List[Dict[str, int]] = []
    rem_months = months
    for idx in range(1, num_installments + 1):
        m_span = min(step_months, rem_months)
        amt = gross_monthly * m_span
        installments.append({
            "installment_index": idx,
            "covered_months": m_span,
            "billing_amount_cents": amt,
        })
        rem_months -= m_span

    next_term_max_monthly = gross_monthly + (gross_monthly * max(0, int(sim.renewal_cap_bps))) // 10000
    requires_dual_sign = disc_bps > 1500 or total_contract_value_cents >= 2_400_000

    return {
        "tenant_name": sim.tenant_name,
        "contract_months": months,
        "billing_cadence": cadence,
        "monthly_breakdown": {
            "base_fee_cents": base_c,
            "raw_overage_cents": raw_ov,
            "discounted_overage_cents": disc_ov,
            "commit_topup_cents": commit_topup,
            "tax_added_cents": tax_res["tax_added_cents"],
            "gross_monthly_cents": gross_monthly,
        },
        "tcv_gross_cents": total_contract_value_cents,
        "installment_schedule": installments,
        "renewal_ceiling_monthly_cents": next_term_max_monthly,
        "requires_finance_dual_sign": requires_dual_sign,
    }


def calculate_sales_rep_quota_attainment(
    closed_deals: List[Dict[str, Any]],
    quarterly_quota_cents: int = 3_000_000,
) -> Dict[str, Any]:
    """核算直销团队季度新签 ACV 配额完成率与加速器提成（100% 以上触发 1.5x 加速）。"""
    quota = max(1, int(quarterly_quota_cents))
    credited_acv = 0
    for d in closed_deals:
        acv = max(0, int(d.get("acv_cents") or 0))
        is_multi_year = int(d.get("contract_months") or 12) >= 24
        weight_bps = 11000 if is_multi_year else 10000
        credited_acv += (acv * weight_bps) // 10000

    attainment_bps = int(round((credited_acv / float(quota)) * 10000))
    base_tier_cents = min(credited_acv, quota)
    accel_tier_cents = max(0, credited_acv - quota)

    base_comm = (base_tier_cents * 600) // 10000      # 6% 基础提成
    accel_comm = (accel_tier_cents * 900) // 10000    # 9% 超额加速提成

    return {
        "quarterly_quota_cents": quota,
        "credited_acv_cents": credited_acv,
        "attainment_bps": attainment_bps,
        "base_commission_cents": base_comm,
        "accelerated_commission_cents": accel_comm,
        "total_payout_cents": base_comm + accel_comm,
    }
