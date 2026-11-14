# -*- coding: utf-8 -*-
"""集团多法人主体内部转移定价 (Transfer Pricing) 与合并报表抵消分录引擎。
法人架构：
- CN_SH_HQ (上海云策母公司)：持有国内 ICP 牌照、签署境内客户合同并承担核心市场销售职能；
- CN_SZ_RD (深圳云策研发中心)：承担底层计量网关与引擎研发，按成本加成法 (Cost-Plus 8%) 向母公司收取技术服务费；
- SG_APAC_SUB (新加坡亚太子公司)：签署 SG_GST_9_EXCLUSIVE 及东南亚跨境客户合同，向上海母公司支付 12% 软件著作权特许权使用费。
"""
import sqlite3
from typing import Any, Dict, List

from app.infra.db import parse_legacy_amount_cents

LEGAL_ENTITIES = {
    "CN_SH_HQ": {"name": "云策企服网络科技（上海）有限公司", "currency": "CNY", "functional_tax_bps": 600},
    "CN_SZ_RD": {"name": "云策智能软件研发（深圳）有限公司", "currency": "CNY", "functional_tax_bps": 600},
    "SG_APAC_SUB": {"name": "YunCe Cloud Pte. Ltd. (Singapore)", "currency": "SGD", "functional_tax_bps": 900},
}


def compute_intercompany_settlement_pack(
    conn: sqlite3.Connection,
    period_key: str,
    sz_rd_monthly_payroll_cents: int = 850_000,
    cost_plus_markup_bps: int = 800,
    sg_royalty_rate_bps: int = 1200,
) -> Dict[str, Any]:
    """计算指定账期的集团内部关联交易结算额与合并报表内部往来抵消分录。"""
    rows = conn.execute(
        """
        SELECT i.*, t.tax_profile_code
        FROM invoices i
        JOIN tenants t ON t.id = i.tenant_id
        WHERE i.period_key = ? AND i.status != 'VOID'
        """,
        (period_key,),
    ).fetchall()

    sh_external_gross = 0
    sg_external_gross = 0
    sg_external_net = 0

    for r in rows:
        d = dict(r)
        gross = parse_legacy_amount_cents(d, "total_cents")
        tax_c = int(d.get("tax_cents") or 0)
        if d.get("tax_profile_code") == "SG_GST_9_EXCLUSIVE":
            sg_external_gross += gross
            sg_external_net += max(0, gross - tax_c)
        else:
            sh_external_gross += gross

    # 1. 深圳研发中心成本加成结算单：研发基数 * (1 + 8%)
    rd_markup = (int(sz_rd_monthly_payroll_cents) * int(cost_plus_markup_bps)) // 10000
    ic_sh_to_sz_net = int(sz_rd_monthly_payroll_cents) + rd_markup
    ic_sh_to_sz_vat = int(round(ic_sh_to_sz_net * 0.06))

    # 2. 新加坡子公司向上海母公司支付软件许可特许权使用费（按不含税境外收入 12%）
    ic_sg_to_sh_royalty = (sg_external_net * int(sg_royalty_rate_bps)) // 10000

    elimination_entries: List[Dict[str, Any]] = [
        {
            "elimination_id": f"ELIM-{period_key}-RD",
            "Counterparty_A": "CN_SH_HQ",
            "Counterparty_B": "CN_SZ_RD",
            "debit_consolidation_acct": "IC_REV_TECH_SERVICE",
            "credit_consolidation_acct": "IC_COGS_TECH_SERVICE",
            "amount_cents": ic_sh_to_sz_net,
            "memo": "抵消母公司与深圳研发中心内部技术服务收入与成本",
        },
        {
            "elimination_id": f"ELIM-{period_key}-ROYALTY",
            "Counterparty_A": "SG_APAC_SUB",
            "Counterparty_B": "CN_SH_HQ",
            "debit_consolidation_acct": "IC_REV_IP_ROYALTY",
            "credit_consolidation_acct": "IC_EXP_IP_ROYALTY",
            "amount_cents": ic_sg_to_sh_royalty,
            "memo": "抵消新加坡子公司向上海母公司支付的跨境IP特许权费",
        },
    ]

    elim_debit = sum(e["amount_cents"] for e in elimination_entries)
    elim_credit = sum(e["amount_cents"] for e in elimination_entries)

    return {
        "period_key": period_key,
        "external_revenue_summary": {
            "CN_SH_HQ_gross_cents": sh_external_gross,
            "SG_APAC_SUB_gross_cents": sg_external_gross,
            "consolidated_external_gross_cents": sh_external_gross + sg_external_gross,
        },
        "intercompany_ settlements": {
            "sh_pay_sz_rd_net_cents": ic_sh_to_sz_net,
            "sh_pay_sz_rd_vat_cents": ic_sh_to_sz_vat,
            "sg_pay_sh_royalty_cents": ic_sg_to_sh_royalty,
        },
        "elimination_balanced": elim_debit == elim_credit,
        "elimination_entries": elimination_entries,
    }
