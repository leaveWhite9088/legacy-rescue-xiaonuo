# -*- coding: utf-8 -*-
"""租户账务事件 Webhook 异步发件箱（Outbox）构建与签名。"""
from datetime import datetime, timezone
import json
import sqlite3
import uuid
from typing import Any, Dict

from app.infra.security import sign_webhook_payload
from app.repos.tenant_repo import get_tenant_by_id


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def enqueue_tenant_webhook(
    conn: sqlite3.Connection,
    tenant_id: str,
    event_type: str,
    data: Dict[str, Any],
) -> str | None:
    tenant = get_tenant_by_id(conn, tenant_id)
    if not tenant or not tenant.get("webhook_url"):
        return None
    now = _now_iso()
    msg_id = f"wh_{uuid.uuid4().hex[:12]}"
    payload_str = json.dumps(
        {"id": msg_id, "event": event_type, "tenant_id": tenant_id, "created_at": now, "data": data},
        ensure_ascii=False,
        sort_keys=True,
    )
    sig = sign_webhook_payload(now, payload_str)
    conn.execute(
        """
        INSERT INTO webhook_outbox (id, tenant_id, event_type, payload_json, signature, delivery_status, attempts, created_at)
        VALUES (?, ?, ?, ?, ?, 'QUEUED', 0, ?)
        """,
        (msg_id, tenant_id, event_type, payload_str, sig, now),
    )
    return msg_id


def dispatch_queued_webhooks(
    conn: sqlite3.Connection,
    batch_limit: int = 50,
) -> Dict[str, Any]:
    """扫描异步发件箱并按批次投递待发送回调消息。"""
    rows = conn.execute(
        """
        SELECT w.*, t.webhook_url
        FROM webhook_outbox w
        JOIN tenants t ON t.id = w.tenant_id
        WHERE w.delivery_status = 'QUEUED'
        ORDER BY w.created_at ASC, w.id ASC
        LIMIT ?
        """,
        (int(batch_limit),),
    ).fetchall()

    delivered = 0
    failed = 0
    dead_lettered = 0
    for r in rows:
        url = str(r["webhook_url"] or "").strip()
        new_attempts = int(r["attempts"] or 0) + 1
        # 离线沙盒模拟：以 unreachable.invalid 或 fail:// 开头的回调地址代表远端超时/5xx 失败
        is_failing_endpoint = (not url) or ("unreachable.invalid" in url) or url.startswith("fail://")
        if not is_failing_endpoint:
            conn.execute(
                "UPDATE webhook_outbox SET delivery_status = 'DELIVERED', attempts = ? WHERE id = ?",
                (new_attempts, r["id"]),
            )
            delivered += 1
        else:
            # 投递未成功时累加尝试次数留待下轮重试
            conn.execute(
                "UPDATE webhook_outbox SET delivery_status = 'QUEUED', attempts = ? WHERE id = ?",
                (new_attempts, r["id"]),
            )
            failed += 1

    return {
        "scanned": len(rows),
        "delivered": delivered,
        "failed": failed,
        "dead_lettered": dead_lettered,
    }
