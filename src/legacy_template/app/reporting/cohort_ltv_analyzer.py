# -*- coding: utf-8 -*-
"""按签约季度划分的租户群组留存矩阵 (Cohort NRR) 与客户终身价值 (LTV) 测算模块。"""
import sqlite3
from typing import Any, Dict, List

from app.infra.db import parse_legacy_amount_cents
from app.utils.calc_helpers import safe_div_bps


def _signup_quarter_label(created_at_iso: str) -> str:
    try:
        year = int(created_at_iso[:4])
        month = int(created_at_iso[5:7])
        q = (month - 1) // 3 + 1
        return f"{year}-Q{q}"
    except Exception:
        return "UNKNOWN"


def analyze_signup_cohorts(conn: sqlite3.Connection, base_period: str = "2026-09", target_period: str = "2026-10") -> List[Dict[str, Any]]:
    tenants = conn.execute("SELECT id, created_at, status FROM tenants ORDER BY created_at ASC").fetchall()
    cohort_tenants: Dict[str, List[str]] = {}
    for t in tenants:
        qlab = _signup_quarter_label(str(t["created_at"]))
        cohort_tenants.setdefault(qlab, []).append(t["id"])

    out: List[Dict[str, Any]] = []
    for qlab in sorted(cohort_tenants.keys()):
        tids = cohort_tenants[qlab]
        placeholders = ",".join("?" for _ in tids)
        b_rows = conn.execute(
            f"SELECT * FROM invoices WHERE period_key = ? AND status != 'VOID' AND tenant_id IN ({placeholders})",
            [base_period, *tids],
        ).fetchall()
        t_rows = conn.execute(
            f"SELECT * FROM invoices WHERE period_key = ? AND status != 'VOID' AND tenant_id IN ({placeholders})",
            [target_period, *tids],
        ).fetchall()
        b_sum = sum(parse_legacy_amount_cents(dict(r), "total_cents") for r in b_rows)
        t_sum = sum(parse_legacy_amount_cents(dict(r), "total_cents") for r in t_rows)
        nrr_bps = safe_div_bps(t_sum, b_sum) if b_sum > 0 else 10000
        out.append({
            "cohort": qlab,
            "tenant_count": len(tids),
            "base_period_cents": b_sum,
            "target_period_cents": t_sum,
            "nrr_bps": nrr_bps,
        })
    return out
