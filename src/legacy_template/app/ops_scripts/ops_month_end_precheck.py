# -*- coding: utf-8 -*-
"""月末财务封账（Month-End Close）前置条件自检脚本。"""
import sqlite3
from typing import Any, Dict, List


def run_month_end_close_precheck(conn: sqlite3.Connection, target_period: str = "2026-11") -> Dict[str, Any]:
    p_row = conn.execute("SELECT * FROM accounting_periods WHERE period_key = ?", (target_period,)).fetchone()
    if not p_row:
        return {"can_close": False, "reason": f"PERIOD_NOT_FOUND:{target_period}", "blockers": ["MISSING_PERIOD"]}

    if p_row["status"] == "CLOSED":
        return {"can_close": False, "reason": "ALREADY_CLOSED", "blockers": ["PERIOD_ALREADY_SEALED"]}

    draft_cnt = conn.execute(
        "SELECT COUNT(*) AS cnt FROM invoices WHERE period_key = ? AND status = 'DRAFT'",
        (target_period,),
    ).fetchone()["cnt"]
    pending_settle_cnt = conn.execute(
        "SELECT COUNT(*) AS cnt FROM invoices WHERE period_key = ? AND status = 'PENDING_SETTLE'",
        (target_period,),
    ).fetchone()["cnt"]
    unmatched_bank_cnt = conn.execute(
        "SELECT COUNT(*) AS cnt FROM bank_statement_imports WHERE status = 'UNMATCHED'"
    ).fetchone()["cnt"]
    pending_approval_cnt = conn.execute(
        "SELECT COUNT(*) AS cnt FROM approval_tickets WHERE status = 'PENDING'"
    ).fetchone()["cnt"]

    blockers: List[str] = []
    if int(draft_cnt or 0) > 0:
        blockers.append(f"UNFINALIZED_DRAFT_INVOICES:{draft_cnt}")
    if int(pending_settle_cnt or 0) > 0:
        blockers.append(f"IN_FLIGHT_PENDING_SETTLE:{pending_settle_cnt}")
    if int(pending_approval_cnt or 0) > 0:
        blockers.append(f"UNRESOLVED_APPROVAL_TICKETS:{pending_approval_cnt}")

    return {
        "target_period": target_period,
        "current_status": p_row["status"],
        "can_close": len(blockers) == 0,
        "blockers": blockers,
        "advisory_unmatched_bank_slips": int(unmatched_bank_cnt or 0),
    }
