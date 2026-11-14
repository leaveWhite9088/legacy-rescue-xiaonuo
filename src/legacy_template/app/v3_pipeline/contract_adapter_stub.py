# -*- coding: utf-8 -*-
"""v3 大客户保底协议与跨境税率适配器桩代码（TODO 状态，尚未实现真实计算）。"""
from typing import Any, Dict


class V3EnterpriseContractStub:
    """架构组占位实现：直接原样返回不含保底补差与不含价外税的净额。
    警告：若强行打开 ENABLE_V3_BILLING_PIPELINE，将导致企业保底合同与跨境价外税全部失效！
    """

    def apply_contract_and_tax(
        self,
        tenant_id: str,
        base_fee_cents: int,
        overage_fee_cents: int,
        tax_profile_code: str = "CN_VAT_6_INCLUSIVE",
    ) -> Dict[str, Any]:
        # Stub: 未查询 enterprise_contracts 表，也未叠加 CN_VAT_6_EXCLUSIVE / SG_GST_9_EXCLUSIVE
        subtotal = int(base_fee_cents) + int(overage_fee_cents)
        return {
            "tenant_id": tenant_id,
            "base_fee_cents": int(base_fee_cents),
            "overage_fee_cents": int(overage_fee_cents),
            "commit_topup_cents": 0,
            "tax_cents": 0,
            "total_cents": subtotal,
            "stub_warning": "v3 contract & tax adapter not implemented yet",
        }
