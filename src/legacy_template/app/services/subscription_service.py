# -*- coding: utf-8 -*-
"""订阅生命周期编排服务：套餐切换、到期退订与手动续期出账。"""
from datetime import datetime, timedelta, timezone
import sqlite3
import uuid
from typing import Any, Dict

from app.domain.pricing import calculate_cycle_bill, calculate_upgrade_proration
from app.domain.quota import get_tenant_quota_snapshot
from app.infra.config import PLANS
from app.infra.runtime_config_loader import get_runtime_bool_flag
from app.infra.events import event_bus
from app.repos.billing_repo import insert_invoice_with_lines
from app.repos.subscription_repo import get_latest_subscription, record_plan_change
from app.services.webhook_dispatcher import enqueue_tenant_webhook


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_subscription_overview(conn: sqlite3.Connection, tenant_id: str, period_key: str) -> Dict[str, Any]:
    sub = get_latest_subscription(conn, tenant_id)
    if not sub:
        raise LookupError("未找到有效订阅")
    quota = get_tenant_quota_snapshot(conn, tenant_id, period_key)
    return {"subscription": dict(sub), "quota": quota}


def change_subscription_plan(
    conn: sqlite3.Connection,
    tenant_id: str,
    new_plan_code: str,
    reason: str = "tenant_change",
) -> Dict[str, Any]:
    if new_plan_code not in PLANS or PLANS[new_plan_code].get("is_legacy"):
        raise ValueError(f"不支持的目标套餐: {new_plan_code}")

    sub = get_latest_subscription(conn, tenant_id)
    if not sub:
        raise LookupError("未找到有效订阅")

    old_plan = sub["plan_code"]
    if old_plan == new_plan_code:
        return {"subscription_id": sub["id"], "old_plan_code": old_plan, "new_plan_code": new_plan_code, "proration_cents": 0}

    now = _now_iso()
    try:
        end_dt = datetime.fromisoformat(sub["cycle_end"].replace("Z", "+00:00"))
        days_rem = max(0, (end_dt - datetime.now(timezone.utc)).days)
    except Exception:
        days_rem = 15

    if get_runtime_bool_flag(conn, "waive_upgrade_proration_promo_window", default=False):
        proration_cents = 0
    else:
        proration_cents = calculate_upgrade_proration(old_plan, new_plan_code, days_rem)
    conn.execute(
        "UPDATE subscriptions SET plan_code = ?, updated_at = ? WHERE id = ?",
        (new_plan_code, now, sub["id"]),
    )
    record_plan_change(conn, sub["id"], tenant_id, old_plan, new_plan_code, now, proration_cents, reason=reason)
    conn.execute(
        "INSERT INTO audit_logs (actor, action, target_id, detail, created_at) VALUES (?, 'CHANGE_PLAN', ?, ?, ?)",
        (tenant_id, sub["id"], f"{old_plan}->{new_plan_code}", now),
    )
    enqueue_tenant_webhook(conn, tenant_id, "subscription.plan_changed", {"old": old_plan, "new": new_plan_code})

    # 发布领域事件通知下游模块（如配额缓存清理等）
    event_bus.publish(
        "subscription.plan_changed",
        {"tenant_id": tenant_id, "subscription_id": sub["id"], "old_plan": old_plan, "new_plan": new_plan_code},
    )

    return {
        "subscription_id": sub["id"],
        "old_plan_code": old_plan,
        "new_plan_code": new_plan_code,
        "proration_cents": proration_cents,
        "effective_at": now,
    }


def cancel_subscription_at_period_end(conn: sqlite3.Connection, tenant_id: str) -> Dict[str, Any]:
    sub = get_latest_subscription(conn, tenant_id)
    if not sub:
        raise LookupError("未找到有效订阅")
    now = _now_iso()
    conn.execute(
        "UPDATE subscriptions SET auto_renew = 0, status = 'CANCELLED_AT_PERIOD_END', updated_at = ? WHERE id = ?",
        (now, sub["id"]),
    )
    enqueue_tenant_webhook(conn, tenant_id, "subscription.cancelled", {"subscription_id": sub["id"]})
    return {
        "subscription_id": sub["id"],
        "status": "CANCELLED_AT_PERIOD_END",
        "refund_cents": 0,
        "note": "当期基础月费不退还，服务保留至周期结束",
    }


def renew_subscription_immediately(conn: sqlite3.Connection, tenant_id: str) -> Dict[str, Any]:
    sub = get_latest_subscription(conn, tenant_id)
    if not sub:
        raise LookupError("未找到有效订阅")

    now = _now_iso()
    period_key = sub["cycle_end"][:7]
    bill = calculate_cycle_bill(conn, tenant_id, period_key, sub["plan_code"])

    inv_id = f"INV-{period_key.replace('-', '')}-{uuid.uuid4().hex[:6].upper()}"
    lines = [
        {"line_type": "BASE_FEE", "description": f"{sub['plan_code']} 周期订阅费", "quantity": 1, "amount_cents": bill["base_fee_cents"]},
    ]
    if bill["overage_fee_cents"] > 0:
        lines.append({"line_type": "OVERAGE", "description": "阶梯超额调用费", "quantity": 1, "amount_cents": bill["overage_fee_cents"]})
    if bill["tax_cents"] > 0:
        lines.append({"line_type": "TAX", "description": "价外增值税/GST", "quantity": 1, "amount_cents": bill["tax_cents"]})

    insert_invoice_with_lines(
        conn,
        {
            "id": inv_id,
            "tenant_id": tenant_id,
            "period_key": period_key,
            "cycle_start": sub["cycle_start"],
            "cycle_end": sub["cycle_end"],
            "plan_code": sub["plan_code"],
            "base_fee_cents": bill["base_fee_cents"],
            "overage_fee_cents": bill["overage_fee_cents"],
            "tax_cents": bill["tax_cents"],
            "late_fee_cents": 0,
            "total_cents": bill["total_cents"],
            "status": "OPEN",
            "created_at": now,
            "updated_at": now,
        },
        lines,
    )

    try:
        old_end = datetime.fromisoformat(sub["cycle_end"].replace("Z", "+00:00"))
    except Exception:
        old_end = datetime.now(timezone.utc)
    new_start = old_end.strftime("%Y-%m-%dT%H:%M:%SZ")
    new_end = (old_end + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute(
        "UPDATE subscriptions SET cycle_start = ?, cycle_end = ?, next_billing_at = ?, status = 'ACTIVE', updated_at = ? WHERE id = ?",
        (new_start, new_end, new_end, now, sub["id"]),
    )
    return {"invoice_id": inv_id, "total_cents": bill["total_cents"], "period_key": period_key}
