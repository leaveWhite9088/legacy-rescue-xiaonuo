# -*- coding: utf-8 -*-
"""[2023 ARCHIVE] 天使轮早期单文件计费计算原型（当时全站仅有 `BASIC_99` 与 `TEAM_399` 两档固定套餐）。"""
from typing import Any, Dict, List


SEED_PLANS_2023 = {
    "BASIC_99": {"monthly_yuan": 99.0, "free_calls": 5000, "extra_yuan_per_1k": 15.0},
    "TEAM_399": {"monthly_yuan": 399.0, "free_calls": 30000, "extra_yuan_per_1k": 10.0},
}


def compute_2023_seed_invoice_yuan(plan_name: str, total_calls: int) -> Dict[str, Any]:
    """2023 原型采用浮点数元计算，这也是 2024 迁移产生 `YUAN_STR` 历史记录的源头背景。"""
    spec = SEED_PLANS_2023.get(plan_name, SEED_PLANS_2023["BASIC_99"])
    over = max(0, int(total_calls) - int(spec["free_calls"]))
    blocks_1k = (over + 999) // 1000
    over_yuan = blocks_1k * float(spec["extra_yuan_per_1k"])
    tot_yuan = round(float(spec["monthly_yuan"]) + over_yuan, 2)
    return {
        "era": "2023_FLOAT_YUAN_ARCHIVED",
        "plan_name": plan_name,
        "base_yuan_str": f"{spec['monthly_yuan']:.2f}",
        "overage_yuan_str": f"{over_yuan:.2f}",
        "total_yuan_str": f"{tot_yuan:.2f}",
    }


def batch_preview_2023_seed_accounts(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "customer_code": r.get("code", "seed_00"),
            **compute_2023_seed_invoice_yuan(str(r.get("plan", "BASIC_99")), int(r.get("calls", 0))),
        }
        for r in rows
    ]
