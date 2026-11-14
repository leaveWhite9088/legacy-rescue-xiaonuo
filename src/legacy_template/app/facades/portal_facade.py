# -*- coding: utf-8 -*-
"""租户自助门户门面：聚合订阅、实时配额、钱包与信用画像。"""
import sqlite3
from typing import Any, Dict

from app.domain.credit_risk import compute_tenant_credit_profile
from app.domain.ledger import get_wallet
from app.services.fapiao_service import get_tenant_fapiao_list
from app.services.subscription_service import (
    cancel_subscription_at_period_end,
    change_subscription_plan,
    get_subscription_overview,
    renew_subscription_immediately,
)


def load_portal_subscription_view(conn: sqlite3.Connection, tenant_id: str, period_key: str) -> Dict[str, Any]:
    return get_subscription_overview(conn, tenant_id, period_key)


def execute_portal_plan_change(conn: sqlite3.Connection, tenant_id: str, new_plan_code: str, reason: str) -> Dict[str, Any]:
    return change_subscription_plan(conn, tenant_id, new_plan_code, reason=reason)


def execute_portal_cancel(conn: sqlite3.Connection, tenant_id: str) -> Dict[str, Any]:
    return cancel_subscription_at_period_end(conn, tenant_id)


def execute_portal_manual_renew(conn: sqlite3.Connection, tenant_id: str) -> Dict[str, Any]:
    return renew_subscription_immediately(conn, tenant_id)


def load_portal_dashboard_bundle(conn: sqlite3.Connection, tenant_id: str, period_key: str) -> Dict[str, Any]:
    sub_view = get_subscription_overview(conn, tenant_id, period_key)
    wallet = get_wallet(conn, tenant_id)
    credit = compute_tenant_credit_profile(conn, tenant_id)
    fapiaos = get_tenant_fapiao_list(conn, tenant_id)
    return {
        **sub_view,
        "wallet": wallet,
        "credit_profile": credit,
        "recent_fapiaos": fapiaos[:10],
    }
