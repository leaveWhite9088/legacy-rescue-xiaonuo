# -*- coding: utf-8 -*-
"""标准 SaaS 订阅主服务协议（MSA）账务核心法务条款摘要库（供客服答复与争议举证引用）。"""
from typing import Dict, Optional


STANDARD_CLAUSES: Dict[str, Dict[str, str]] = {
    "MSA-4.2-PROGRESSIVE-TIERS": {
        "title": "第 4.2 条 超额累进阶梯计费",
        "summary": "超出套餐内含调用配额的部分，严格按照各超额区间对应单价分段累加计费，不因跨入高阶区间而下调前序区间历史单价。",
    },
    "MSA-5.1-NO-MIDCYCLE-REFUND": {
        "title": "第 5.1 条 期中退订与降配生效规则",
        "summary": "客户在已开启的计费周期内主动申请取消自动续费或降低套餐档位的，当前周期已收取或应付的基础月租不予按天折算退还，权益保留至当期届满。",
    },
    "MSA-6.3-EXCLUSIVE-TAX": {
        "title": "第 6.3 条 价外增值税与跨境商品服务税",
        "summary": "签署不含税框架协议（CN_VAT_6_EXCLUSIVE / SG_GST_9_EXCLUSIVE）的客户，结算账单在税前净额之上依法另行计收适用增值税或消费税。",
    },
    "MSA-7.4-LATE-PAYMENT-FEE": {
        "title": "第 7.4 条 逾期付款违约滞纳金",
        "summary": "账单逾越到期付款日仍未结清的，平台有权按应付账单总额的 5% 统一计收逾期违约金，不设行业或客户等级豁免。",
    },
    "MSA-9.1-LEGACY-GRANDFATHERING": {
        "title": "第 9.1 条 2024 早期存量合同延续保护",
        "summary": "2024 年度签署早期包干协议且持续履约未中断的存量租户（ACTIVE_LEGACY），在原协议存续期内维持原计费公式与优惠条款不变。",
    },
}


def lookup_msa_clause(clause_id: str) -> Optional[Dict[str, str]]:
    item = STANDARD_CLAUSES.get(clause_id)
    return dict(item) if item else None
