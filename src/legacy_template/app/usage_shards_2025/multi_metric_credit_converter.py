# -*- coding: utf-8 -*-
"""异构资源指标（API_CALLS / GPU_A100_SEC / LLM_1K_TOKENS / STORAGE_GB_DAY）统一折算标准计费点算子。"""
from typing import Any, Dict, List


METRIC_EQUIVALENCE_FACTORS = {
    "API_CALLS": (1, 1),          # 1 次 = 1 标准点
    "LLM_1K_TOKENS": (15, 1),     # 1K Tokens = 15 标准点
    "GPU_A100_SEC": (120, 1),     # 1 秒 A100 = 120 标准点
    "STORAGE_GB_DAY": (5, 2),     # 1 GB*天 = 2.5 标准点（向上取整）
}


def normalize_heterogeneous_usage_batch(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_metric: Dict[str, int] = {}
    total_standard_units = 0
    for r in records:
        m = str(r.get("metric_code") or "API_CALLS").upper()
        raw_qty = max(0, int(r.get("quantity") or 0))
        num, den = METRIC_EQUIVALENCE_FACTORS.get(m, (1, 1))
        norm = (raw_qty * num + den - 1) // den
        by_metric[m] = by_metric.get(m, 0) + norm
        total_standard_units += norm
    return {
        "total_normalized_units": total_standard_units,
        "normalized_by_metric": by_metric,
    }
