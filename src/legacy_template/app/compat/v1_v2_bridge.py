# -*- coding: utf-8 -*-
"""v1 与 v2 核心账务模型桥接器：
1. 承接 2024 ACTIVE_LEGACY 存量老租户算价请求并转发至 legacy_v1.v1_flat_tariff；
2. 为异步计量刷盘任务解析归属套餐代码；
3. 为老版管理报表转换混合货币字段。
"""
import sqlite3
from typing import Any, Dict

from app.infra.config import FEATURE_FLAGS, PLANS
from app.legacy_v1.v1_currency_shim import format_v1_yuan_display, parse_v1_yuan_string
from app.legacy_v1.v1_flat_tariff import compute_v1_legacy_contract_bill


def is_legacy_v1_subscription(tenant_dict: Dict[str, Any], sub_row: Any) -> bool:
    if not FEATURE_FLAGS.get("ENABLE_LEGACY_V1_COMPAT_BRIDGE", True):
        return False
    if tenant_dict.get("is_legacy_v1"):
        return True
    if sub_row is not None and "legacy_contract_override" in sub_row.keys() and sub_row["legacy_contract_override"]:
        return True
    if sub_row is not None and sub_row["plan_code"] == "LEGACY_FLAT_99":
        return True
    return False


def calculate_v1_bridge_bill(
    tenant_dict: Dict[str, Any],
    sub_row: sqlite3.Row,
    total_usage: int,
) -> Dict[str, Any]:
    """通过 v1 兼容桥调用 2024 存量包干及合同覆盖计费逻辑。"""
    plan_code = sub_row["plan_code"]
    fallback_plan = PLANS.get(plan_code, PLANS["LEGACY_FLAT_99"])
    return compute_v1_legacy_contract_bill(
        tenant_dict=tenant_dict,
        sub_row=sub_row,
        total_usage=total_usage,
        fallback_plan_def=fallback_plan,
    )


def resolve_flush_plan_code(conn: sqlite3.Connection, event_row: sqlite3.Row) -> str:
    """刷盘时解析计量事件应归入的套餐分段代码。"""
    tenant_id = event_row["tenant_id"]
    sub = conn.execute(
        "SELECT plan_code FROM subscriptions WHERE tenant_id = ? ORDER BY updated_at DESC LIMIT 1",
        (tenant_id,),
    ).fetchone()
    return sub["plan_code"] if sub else "STARTER"


def format_hybrid_invoice_amount(inv_dict: Dict[str, Any]) -> Dict[str, Any]:
    eff_cents = parse_v1_yuan_string(inv_dict.get("raw_legacy_total"), int(inv_dict.get("total_cents") or 0))
    return {
        "effective_total_cents": eff_cents,
        "display_yuan": format_v1_yuan_display(eff_cents, with_symbol=True),
        "is_yuan_str_origin": inv_dict.get("currency_unit") == "YUAN_STR",
    }
