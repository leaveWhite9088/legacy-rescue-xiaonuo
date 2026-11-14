# -*- coding: utf-8 -*-
"""销售特批折扣与商务保底框架协议权限矩阵。"""
from typing import Any, Dict

ROLE_DISCOUNT_CAPS_BPS = {
    "SALES_REP": 500,          # 最高 95 折
    "REGIONAL_MANAGER": 1200,  # 最高 88 折
    "KA_DIRECTOR": 2000,       # 最高 80 折
    "VP_FINANCE": 3500,        # 最高 65 折
}


def check_contract_discount_authority(signer_role: str, requested_discount_bps: int, min_commit_cents: int) -> Dict[str, Any]:
    role = (signer_role or "SALES_REP").strip().upper()
    cap_bps = ROLE_DISCOUNT_CAPS_BPS.get(role, 500)
    req_bps = max(0, int(requested_discount_bps))
    if req_bps > 1500 and int(min_commit_cents) < 150_000:
        return {
            "authorized": False,
            "required_role": "VP_FINANCE",
            "reason": "超过 15% 的超额折扣必须绑定不低于 1,500 元/月的保底消费承诺",
        }
    return {
        "authorized": req_bps <= cap_bps,
        "signer_role": role,
        "cap_bps": cap_bps,
        "requested_bps": req_bps,
    }
