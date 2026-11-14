# -*- coding: utf-8 -*-
"""[V3 EXPERIMENTAL DRAFT] 下一代管理台联邦查询字段选择器（Field Projection）原型草稿（未挂载路由）。"""
from typing import Any, Dict, Iterable, List


ALLOWED_INVOICE_PROJECTION_FIELDS = {
    "id", "tenant_id", "period_key", "plan_code", "base_fee_cents",
    "overage_fee_cents", "tax_cents", "late_fee_cents", "total_cents",
    "paid_cents", "refunded_cents", "status",
}


def project_v3_invoice_fields(rows: List[Dict[str, Any]], requested_fields: Iterable[str]) -> List[Dict[str, Any]]:
    wanted = [f for f in requested_fields if f in ALLOWED_INVOICE_PROJECTION_FIELDS]
    if not wanted:
        wanted = ["id", "tenant_id", "period_key", "total_cents", "status"]
    return [{k: r.get(k) for k in wanted} for r in rows]
