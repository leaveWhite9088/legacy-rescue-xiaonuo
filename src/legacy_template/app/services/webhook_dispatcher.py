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
