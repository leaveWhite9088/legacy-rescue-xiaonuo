# -*- coding: utf-8 -*-
"""智能催收与逾期信用分级管控引擎（v2 生产模块）。"""
from datetime import datetime, timezone
import sqlite3
from typing import Any, Dict, List

from app.domain.pricing import compute_late_fee_cents
from app.infra.config import DUNNING_STAGE_POLICY
from app.infra.db import parse_legacy_amount_cents
from app.repos.dunning_repo import upsert_dunning_case
from app.repos.tenant_repo import get_active_enterprise_contract


def _calc_overdue_days(cycle_end_iso: str, as_of_iso: str) -> int:
    try:
        dt_end = datetime.fromisoformat(cycle_end_iso.replace("Z", "+00:00"))
        dt_now = datetime.fromisoformat(as_of_iso.replace("Z", "+00:00"))
        return max(0, (dt_now - dt_end).days)
    except Exception:
        return 0


def resolve_dunning_stage(overdue_days: int) -> Dict[str, Any]:
    if overdue_days <= 0:
        return {"stage": "CURRENT", "throttle_pct": 0, "channel": "NONE"}
    for rule in DUNNING_STAGE_POLICY:
        if rule["min_overdue_days"] <= overdue_days <= rule["max_overdue_days"]:
            return {
                "stage": rule["stage"],
                "throttle_pct": int(rule["throttle_pct"]),
                "channel": rule["channel"],
            }
    last = DUNNING_STAGE_POLICY[-1]
    return {"stage": last["stage"], "throttle_pct": int(last["throttle_pct"]), "channel": last["channel"]}


def evaluate_overdue_portfolio(
    conn: sqlite3.Connection,
    as_of_iso: str = "2026-11-14T00:00:00Z",
    persist_cases: bool = False,
) -> Dict[str, Any]:
    """扫描所有未结清且超过账期结束日的账单，结合大客户授信额度评估催收阶段与建议滞纳金。"""
    rows = conn.execute(
        """
        SELECT i.*, t.company_name, t.tier_level
        FROM invoices i
        JOIN tenants t ON t.id = i.tenant_id
        WHERE i.status IN ('OPEN', 'PENDING_SETTLE')
        ORDER BY i.cycle_end ASC
        """
    ).fetchall()

    evaluated: List[Dict[str, Any]] = []
    stage_distribution: Dict[str, int] = {}

    for r in rows:
        d = dict(r)
        overdue_days = _calc_overdue_days(str(d["cycle_end"]), as_of_iso)
        if overdue_days <= 0:
            continue
        eff_total = parse_legacy_amount_cents(d, "total_cents")
        unpaid = max(0, eff_total - int(d["paid_cents"] or 0))
        if unpaid <= 0:
            continue

        contract = get_active_enterprise_contract(conn, d["tenant_id"])
        credit_limit = int(contract["credit_limit_cents"]) if contract else 0
        stage_info = resolve_dunning_stage(overdue_days)

        # 若签有授信额度且未付总额在授信额度以内，则豁免接口限流，但滞纳金照章计提
        effective_throttle = 0 if (credit_limit >= unpaid and overdue_days <= 14) else stage_info["throttle_pct"]
        suggested_late_fee = compute_late_fee_cents(unpaid, is_overdue=True)

        stage_name = stage_info["stage"]
        stage_distribution[stage_name] = stage_distribution.get(stage_name, 0) + 1

        item = {
            "case_id": f"dun_{d['id']}",
            "invoice_id": d["id"],
            "tenant_id": d["tenant_id"],
            "company_name": d["company_name"],
            "overdue_days": overdue_days,
            "unpaid_cents": unpaid,
            "suggested_late_fee_cents": suggested_late_fee,
            "stage": stage_name,
            "effective_throttle_pct": effective_throttle,
            "credit_shield_applied": credit_limit >= unpaid,
        }
        evaluated.append(item)

        if persist_cases:
            upsert_dunning_case(
                conn,
                {
                    "id": item["case_id"],
                    "tenant_id": d["tenant_id"],
                    "invoice_id": d["id"],
                    "stage": stage_name,
                    "overdue_days": overdue_days,
                    "unpaid_cents": unpaid,
                    "last_notified_at": as_of_iso,
                    "status": "OPEN",
                    "updated_at": as_of_iso,
                },
            )

    return {
        "as_of": as_of_iso,
        "overdue_count": len(evaluated),
        "stage_distribution": stage_distribution,
        "total_overdue_cents": sum(x["unpaid_cents"] for x in evaluated),
        "cases": evaluated,
    }
