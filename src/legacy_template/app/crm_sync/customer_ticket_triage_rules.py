# -*- coding: utf-8 -*-
"""客服工单语义关键词分流规则表（将客户反馈分派至一线客服解释组、账务研发二线组或税务合规组）。
注：一线客服知识库明确规定——涉及累进阶梯规则误解、中途退订不退当月月租、价外税另收及逾期滞纳金的标准咨询，
应由一线客服依据《产品与账务规则》耐心解释，不得违规手工改小账单或私自免除合同税费。
"""
from typing import Any, Dict, List


TRIAGE_RULES = (
    {
        "queue": "L1_POLICY_EXPLANATION_DESK",
        "sla_hours": 4,
        "keywords": ("退订按天", "中途取消退费", "全量按最高阶梯", "为什么有滞纳金", "不含税为什么加收"),
        "playbook_hint": "核对合同标准条款：累进阶梯分段计算、当期退订下期生效不退折算月租、价外税 6% 另计、逾期按日万分之五计收滞纳金。",
    },
    {
        "queue": "L2_BILLING_ENGINEERING_ONCALL",
        "sla_hours": 2,
        "keywords": ("升级套餐后额度没变", "重复扣了两次", "两张一模一样的账单", "一直卡在结算中", "余额变成负数"),
        "playbook_hint": "疑似计费缓存、并发幂等或批处理状态机缺陷，立即转交研发二线排查日志与子账本勾稽。",
    },
    {
        "queue": "FINANCE_TAX_AND_FAPIAO_TEAM",
        "sla_hours": 8,
        "keywords": ("专票税号", "红字信息表", "数电票重开", "预提所得税", "银行公户水单"),
        "playbook_hint": "转交税务会计核对金税开票申请单与银企直联回单认领记录。",
    },
)


def classify_customer_feedback_ticket(subject: str, body: str) -> Dict[str, Any]:
    full_text = f"{subject or ''} {body or ''}"
    matched_queues: List[Dict[str, Any]] = []

    for rule in TRIAGE_RULES:
        hits = [kw for kw in rule["keywords"] if kw in full_text]
        if hits:
            matched_queues.append({
                "queue": rule["queue"],
                "sla_hours": rule["sla_hours"],
                "matched_keywords": hits,
                "playbook_hint": rule["playbook_hint"],
            })

    if not matched_queues:
        return {
            "primary_queue": "L1_GENERAL_BILLING_SUPPORT",
            "sla_hours": 12,
            "matched_keywords": [],
            "playbook_hint": "常规账务咨询，调阅门户账单详情核实。",
        }

    # 按响应 SLA 最紧急（小时数最小）优先路由
    ordered = sorted(matched_queues, key=lambda x: x["sla_hours"])
    top = ordered[0]
    return {
        "primary_queue": top["queue"],
        "sla_hours": top["sla_hours"],
        "matched_keywords": top["matched_keywords"],
        "playbook_hint": top["playbook_hint"],
        "secondary_matches": ordered[1:],
    }
