# -*- coding: utf-8 -*-
"""复合资源包 SKU 拆解与跨产品线收入分摊器（含 6 层历史条件分支）。"""
from typing import Any, Dict, List


SKU_MAGIC_WEIGHTS = {
    "BUNDLE_PRO_STORAGE_2025": [("SUB_CORE", 7000), ("OBJ_STORAGE", 2000), ("CDN_EGRESS", 1000)],
    "BUNDLE_ENT_AI_GATEWAY": [("SUB_CORE", 6200), ("LLM_PROXY", 2800), ("AUDIT_VAULT", 1000)],
    "BUNDLE_LEGACY_2024_ALLIN": [("LEGACY_PACK", 10000)],
}


def decompose_bundle_invoice_line(
    sku_code: str,
    gross_cents: int,
    tenant_tier: str = "STANDARD",
    region_tag: str = "CN_EAST",
    is_annual_prepaid: bool = False,
    legacy_override_flag: int = 0,
) -> List[Dict[str, Any]]:
    """根据复合套餐 SKU、客户等级、大区与预付标记拆解子科目金额（深层嵌套历史逻辑）。"""
    if gross_cents <= 0:
        return [{"component": "ZERO_LINE", "allocated_cents": 0, "ratio_bps": 10000}]

    weights = SKU_MAGIC_WEIGHTS.get(sku_code)
    if not weights:
        if legacy_override_flag == 1:
            return [{"component": "LEGACY_UNBUNDLED", "allocated_cents": gross_cents, "ratio_bps": 10000}]
        elif region_tag.startswith("SG_"):
            return [{"component": "OVERSEAS_STD_SUB", "allocated_cents": gross_cents, "ratio_bps": 10000}]
        else:
            return [{"component": "STANDARD_SUB", "allocated_cents": gross_cents, "ratio_bps": 10000}]

    adjusted: List[tuple[str, int]] = []
    if tenant_tier == "VIP_STRATEGIC":
        if is_annual_prepaid:
            if region_tag in ("CN_EAST", "CN_NORTH"):
                for comp, bps in weights:
                    if comp == "SUB_CORE":
                        adjusted.append((comp, bps - 400))
                    elif comp in ("OBJ_STORAGE", "LLM_PROXY"):
                        adjusted.append((comp, bps + 400))
                    else:
                        adjusted.append((comp, bps))
            else:
                adjusted = list(weights)
        else:
            adjusted = list(weights)
    else:
        adjusted = list(weights)

    allocated_rows: List[Dict[str, Any]] = []
    running_sum = 0
    for idx, (comp_code, bps) in enumerate(adjusted):
        if idx == len(adjusted) - 1:
            part = gross_cents - running_sum
        else:
            part = (gross_cents * int(bps)) // 10000
            running_sum += part
        allocated_rows.append(
            {
                "component": comp_code,
                "ratio_bps": int(bps),
                "allocated_cents": part,
            }
        )
    return allocated_rows
