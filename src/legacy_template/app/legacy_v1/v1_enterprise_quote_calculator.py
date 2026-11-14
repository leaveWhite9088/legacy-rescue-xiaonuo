# -*- coding: utf-8 -*-
"""2024 第一代销售商务报价器 (CPQ v1) 与非标私有云附加包测算引擎 (LEGACY MODULE)。
背景：2024 年销售团队通过本模块生成多年度阶梯合同、独立集群资源附加包、席位授权费与毛利底线测算单。
2025 Q2 标准 SaaS 自助化后，线上自动出账已迁移至 app.domain.pricing 与 app.domain.contracts；
本模块保留在 legacy_v1 中供历史框架合同重算核对与离线商务报价单打印使用。
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.legacy_v1.v1_currency_shim import format_v1_yuan_display

V1_ADDON_CATALOG_2024: Dict[str, Dict[str, Any]] = {
    "DEDICATED_VPC_NODE": {
        "sku": "DEDICATED_VPC_NODE",
        "title": "独享VPC计算节点附加包",
        "unit_monthly_cents": 120_000,
        "direct_cost_cents": 48_000,
        "discountable": True,
    },
    "AUDIT_LOG_ARCHIVE_3Y": {
        "sku": "AUDIT_LOG_ARCHIVE_3Y",
        "title": "金融级三年冷备审计日志留存",
        "unit_monthly_cents": 35_000,
        "direct_cost_cents": 8_500,
        "discountable": True,
    },
    "DEDICATED_TAM_SUPPORT": {
        "sku": "DEDICATED_TAM_SUPPORT",
        "title": "专属技术客户经理(7x24响应)",
        "unit_monthly_cents": 250_000,
        "direct_cost_cents": 165_000,
        "discountable": False,
    },
    "CUSTOM_SSO_SAML": {
        "sku": "CUSTOM_SSO_SAML",
        "title": "企业级SAML2.0/LDAP单点登录模块",
        "unit_monthly_cents": 29_900,
        "direct_cost_cents": 3_000,
        "discountable": True,
    },
    "CROSS_REGION_DR": {
        "sku": "CROSS_REGION_DR",
        "title": "同城双活与异地灾备同步链路",
        "unit_monthly_cents": 180_000,
        "direct_cost_cents": 79_000,
        "discountable": True,
    },
}

V1_BASE_PLAN_COSTS_2024: Dict[str, Dict[str, int]] = {
    "LEGACY_FLAT_99": {"list_monthly_cents": 9_900, "cogs_cents": 2_100, "included_seats": 5},
    "STARTER": {"list_monthly_cents": 19_900, "cogs_cents": 3_500, "included_seats": 10},
    "PRO": {"list_monthly_cents": 59_900, "cogs_cents": 11_000, "included_seats": 30},
    "ENTERPRISE": {"list_monthly_cents": 199_900, "cogs_cents": 42_000, "included_seats": 100},
}


@dataclass
class V1AddonSelection:
    sku: str
    quantity: int = 1
    override_discount_bps: Optional[int] = None


@dataclass
class V1RampYearSpec:
    year_index: int
    months: int
    seat_count: int
    committed_api_calls_monthly: int
    headline_discount_bps: int = 0
    addons: List[V1AddonSelection] = field(default_factory=list)


class LegacyEnterpriseQuoteEngineV1:
    """2024 销售商务台账多年度爬坡合同（Ramp Deal）试算器。"""

    EXTRA_SEAT_PRICE_CENTS = 1_500
    EXTRA_SEAT_COGS_CENTS = 220
    MIN_GROSS_MARGIN_BPS = 5500  # 低于 55% 毛利强制要求 CFO 特批

    def evaluate_single_year(self, plan_code: str, spec: V1RampYearSpec) -> Dict[str, Any]:
        if spec.months <= 0 or spec.months > 24:
            raise ValueError("Ramp period months must be between 1 and 24")
        plan_meta = V1_BASE_PLAN_COSTS_2024.get(plan_code, V1_BASE_PLAN_COSTS_2024["ENTERPRISE"])
        disc_bps = max(0, min(5000, int(spec.headline_discount_bps)))

        list_base_m = int(plan_meta["list_monthly_cents"])
        net_base_m = list_base_m - (list_base_m * disc_bps) // 10000
        cogs_base_m = int(plan_meta["cogs_cents"])

        extra_seats = max(0, int(spec.seat_count) - int(plan_meta["included_seats"]))
        list_seat_m = extra_seats * self.EXTRA_SEAT_PRICE_CENTS
        net_seat_m = list_seat_m - (list_seat_m * disc_bps) // 10000
        cogs_seat_m = extra_seats * self.EXTRA_SEAT_COGS_CENTS

        addon_lines: List[Dict[str, Any]] = []
        list_addon_m = 0
        net_addon_m = 0
        cogs_addon_m = 0

        for item in spec.addons:
            cat = V1_ADDON_CATALOG_2024.get(item.sku)
            if not cat or item.quantity <= 0:
                continue
            qty = int(item.quantity)
            raw_m = int(cat["unit_monthly_cents"]) * qty
            item_disc = (
                int(item.override_discount_bps)
                if item.override_discount_bps is not None
                else (disc_bps if cat["discountable"] else 0)
            )
            item_disc = max(0, min(4000, item_disc))
            eff_m = raw_m - (raw_m * item_disc) // 10000
            cost_m = int(cat["direct_cost_cents"]) * qty

            list_addon_m += raw_m
            net_addon_m += eff_m
            cogs_addon_m += cost_m
            addon_lines.append({
                "sku": item.sku,
                "title": cat["title"],
                "quantity": qty,
                "list_monthly_cents": raw_m,
                "applied_discount_bps": item_disc,
                "net_monthly_cents": eff_m,
                "cogs_monthly_cents": cost_m,
            })

        monthly_list_total = list_base_m + list_seat_m + list_addon_m
        monthly_net_total = net_base_m + net_seat_m + net_addon_m
        monthly_cogs_total = cogs_base_m + cogs_seat_m + cogs_addon_m

        period_list_tcv = monthly_list_total * int(spec.months)
        period_net_tcv = monthly_net_total * int(spec.months)
        period_cogs = monthly_cogs_total * int(spec.months)
        gross_profit = period_net_tcv - period_cogs
        margin_bps = int(round((gross_profit / float(period_net_tcv)) * 10000)) if period_net_tcv > 0 else 0

        return {
            "year_index": spec.year_index,
            "months": spec.months,
            "seat_count": spec.seat_count,
            "extra_seats": extra_seats,
            "monthly_list_cents": monthly_list_total,
            "monthly_net_cents": monthly_net_total,
            "period_list_tcv_cents": period_list_tcv,
            "period_net_tcv_cents": period_net_tcv,
            "period_cogs_cents": period_cogs,
            "gross_profit_cents": gross_profit,
            "gross_margin_bps": margin_bps,
            "addons": addon_lines,
        }

    def build_multi_year_deal_sheet(
        self,
        customer_name: str,
        plan_code: str,
        ramp_years: List[V1RampYearSpec],
        payment_terms: str = "ANNUAL_PREPAID",
    ) -> Dict[str, Any]:
        if not ramp_years:
            raise ValueError("At least one ramp year specification is required")

        year_reports = [self.evaluate_single_year(plan_code, y) for y in ramp_years]
        total_months = sum(r["months"] for r in year_reports)
        list_tcv = sum(r["period_list_tcv_cents"] for r in year_reports)
        net_tcv = sum(r["period_net_tcv_cents"] for r in year_reports)
        total_cogs = sum(r["period_cogs_cents"] for r in year_reports)

        if payment_terms == "QUARTERLY_PREPAID":
            # 季付较年付上浮 3% 资金占用费
            surcharge = (net_tcv * 300) // 10000
            net_tcv += surcharge
        elif payment_terms == "MONTHLY_ARREARS":
            surcharge = (net_tcv * 600) // 10000
            net_tcv += surcharge

        blended_margin_bps = (
            int(round(((net_tcv - total_cogs) / float(net_tcv)) * 10000)) if net_tcv > 0 else 0
        )
        blended_discount_bps = (
            int(round(((list_tcv - net_tcv) / float(list_tcv)) * 10000)) if list_tcv > 0 else 0
        )
        acv_cents = int(round(net_tcv * (12.0 / max(1, total_months))))

        approval_tier = "AUTO_SALES_DESK"
        if blended_margin_bps < self.MIN_GROSS_MARGIN_BPS:
            approval_tier = "CFO_MANDATORY_SIGN"
        elif blended_discount_bps > 2000 or net_tcv >= 5_000_000:
            approval_tier = "VP_SALES_AND_FINANCE"
        elif blended_discount_bps > 1000:
            approval_tier = "REGIONAL_DIRECTOR"

        return {
            "customer_name": customer_name,
            "plan_code": plan_code,
            "payment_terms": payment_terms,
            "total_months": total_months,
            "list_tcv_cents": list_tcv,
            "net_tcv_cents": net_tcv,
            "acv_cents": acv_cents,
            "blended_discount_bps": max(0, blended_discount_bps),
            "blended_gross_margin_bps": blended_margin_bps,
            "required_approval_tier": approval_tier,
            "years": year_reports,
        }

    def render_quote_ascii_preview(self, deal_sheet: Dict[str, Any]) -> str:
        lines = [
            "=" * 74,
            f"YUNCE CPQ V1 ENTERPRISE QUOTE SHEET - {deal_sheet['customer_name']}",
            "-" * 74,
            f"Base Plan      : {deal_sheet['plan_code']:<18} Payment Terms : {deal_sheet['payment_terms']}",
            f"Contract Term  : {deal_sheet['total_months']} Months          Approval Gate : {deal_sheet['required_approval_tier']}",
            f"Net TCV        : {format_v1_yuan_display(deal_sheet['net_tcv_cents'], True, True)}",
            f"Annualized ACV : {format_v1_yuan_display(deal_sheet['acv_cents'], True, True)}",
            f"Gross Margin   : {deal_sheet['blended_gross_margin_bps'] / 100.0:.2f}%",
            "-" * 74,
        ]
        for yr in deal_sheet["years"]:
            lines.append(
                f"Year {yr['year_index']} ({yr['months']}m, {yr['seat_count']} seats): "
                f"Monthly={format_v1_yuan_display(yr['monthly_net_cents'])} | "
                f"Subtotal={format_v1_yuan_display(yr['period_net_tcv_cents'])}"
            )
        lines.append("=" * 74)
        return "\n".join(lines)
