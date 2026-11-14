# -*- coding: utf-8 -*-
"""财务内控双人复核审批流引擎（针对大额跨期调账、大额退费、授信特批）。"""
from datetime import datetime, timezone
import sqlite3
import uuid
from typing import Any, Dict, List, Optional

from app.infra.config import FEATURE_FLAGS
from app.repos.approval_repo import (
    create_approval_ticket,
    get_approval_ticket,
    list_approval_tickets,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def submit_finance_approval(
    conn: sqlite3.Connection,
    ticket_type: str,
    tenant_id: str,
    ref_object_id: str,
    amount_cents: int,
    requested_by: str,
    reason: str,
) -> Dict[str, Any]:
    threshold = int(FEATURE_FLAGS.get("APPROVAL_DUAL_SIGN_THRESHOLD_CENTS", 500_000))
    req_count = 2 if abs(int(amount_cents)) >= threshold else 1
    now = _now_iso()
    tid = f"APR-{uuid.uuid4().hex[:8].upper()}"
    ticket = {
        "id": tid,
        "ticket_type": ticket_type,
        "tenant_id": tenant_id,
        "ref_object_id": ref_object_id,
        "amount_cents": int(amount_cents),
        "requested_by": requested_by,
        "required_approvals": req_count,
        "reason": reason,
        "created_at": now,
        "updated_at": now,
    }
    create_approval_ticket(conn, ticket)
    return get_approval_ticket(conn, tid) or ticket


def decide_finance_approval(
    conn: sqlite3.Connection,
    ticket_id: str,
    approver: str,
    decision: str,
) -> Dict[str, Any]:
    t = get_approval_ticket(conn, ticket_id)
    if not t:
        raise LookupError("审批单不存在")
    if t["status"] in ("APPROVED", "REJECTED"):
        raise ValueError(f"审批单已终审结束: {t['status']}")
    if approver == t["requested_by"]:
        raise PermissionError("申请人本人不得审批自己发起的财务工单（职责分离原则）")

    now = _now_iso()
    dec = decision.strip().upper()
    if dec == "REJECT":
        conn.execute(
            "UPDATE approval_tickets SET status = 'REJECTED', updated_at = ? WHERE id = ?",
            (now, ticket_id),
        )
        return get_approval_ticket(conn, ticket_id)  # type: ignore

    if int(t["required_approvals"]) == 1:
        conn.execute(
            "UPDATE approval_tickets SET first_approver = ?, status = 'APPROVED', updated_at = ? WHERE id = ?",
            (approver, now, ticket_id),
        )
    else:
        if not t["first_approver"]:
            conn.execute(
                "UPDATE approval_tickets SET first_approver = ?, status = 'FIRST_APPROVED', updated_at = ? WHERE id = ?",
                (approver, now, ticket_id),
            )
        else:
            if t["first_approver"] == approver:
                raise PermissionError("大额双签工单必须由两名不同财务审批人会签")
            conn.execute(
                "UPDATE approval_tickets SET second_approver = ?, status = 'APPROVED', updated_at = ? WHERE id = ?",
                (approver, now, ticket_id),
            )

    return get_approval_ticket(conn, ticket_id)  # type: ignore


def query_approval_tickets(conn: sqlite3.Connection, status: Optional[str] = None) -> List[Dict[str, Any]]:
    return list_approval_tickets(conn, status=status)
