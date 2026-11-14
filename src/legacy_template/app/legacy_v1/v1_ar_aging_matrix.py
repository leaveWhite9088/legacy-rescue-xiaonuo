# -*- coding: utf-8 -*-
"""2024 应收账款账龄矩阵与坏账准备计提试算模块（老版财务月报遗留）。"""
from datetime import datetime, timezone
import sqlite3
from typing import Any, Dict, List

from app.legacy_v1.v1_currency_shim import parse_v1_yuan_string

BAD_DEBT_PROVISION_RATES_BPS = {
    "CURRENT": 0,
    "1_30_DAYS": 100,     # 1%
    "31_60_DAYS": 500,    # 5%
    "61_90_DAYS": 2000,   # 20%
    "91_180_DAYS": 5000,  # 50%
    "OVER_180_DAYS": 10000,
}


def _days_between_iso(older_iso: str, newer_iso: str) -> int:
    try:
        d1 = datetime.fromisoformat(older_iso.replace("Z", "+00:00"))
        d2 = datetime.fromisoformat(newer_iso.replace("Z", "+00:00"))
        return max(0, (d2 - d1).days)
    except Exception:
        return 0


def classify_v1_aging_bucket(age_days: int) -> str:
    if age_days <= 0:
        return "CURRENT"
    if age_days <= 30:
        return "1_30_DAYS"
    if age_days <= 60:
        return "31_60_DAYS"
    if age_days <= 90:
        return "61_90_DAYS"
    if age_days <= 180:
        return "91_180_DAYS"
    return "OVER_180_DAYS"


def generate_v1_ar_aging_report(conn: sqlite3.Connection, as_of_iso: str = "2026-11-14T00:00:00Z") -> Dict[str, Any]:
    rows = conn.execute(
        """
        SELECT i.id, i.tenant_id, i.period_key, i.cycle_end, i.total_cents,
               i.paid_cents, i.currency_unit, i.raw_legacy_total, i.status,
               t.company_name, t.tier_level
        FROM invoices i
        JOIN tenants t ON t.id = i.tenant_id
        WHERE i.status IN ('OPEN', 'PENDING_SETTLE', 'DISPUTED')
        ORDER BY i.cycle_end ASC
        """
    ).fetchall()

    buckets_cents: Dict[str, int] = {k: 0 for k in BAD_DEBT_PROVISION_RATES_BPS}
    provision_cents = 0
    details: List[Dict[str, Any]] = []

    for r in rows:
        d = dict(r)
        gross = parse_v1_yuan_string(d.get("raw_legacy_total"), int(d.get("total_cents") or 0))
        outstanding = max(0, gross - int(d.get("paid_cents") or 0))
        if outstanding <= 0:
            continue
        age_days = _days_between_iso(str(d["cycle_end"]), as_of_iso)
        b_key = classify_v1_aging_bucket(age_days)
        buckets_cents[b_key] += outstanding
        prov = (outstanding * BAD_DEBT_PROVISION_RATES_BPS[b_key]) // 10000
        provision_cents += prov
        details.append({
            "invoice_id": d["id"],
            "tenant_id": d["tenant_id"],
            "company_name": d["company_name"],
            "age_days": age_days,
            "bucket": b_key,
            "outstanding_cents": outstanding,
            "provision_cents": prov,
        })

    return {
        "as_of": as_of_iso,
        "total_outstanding_cents": sum(buckets_cents.values()),
        "total_bad_debt_provision_cents": provision_cents,
        "buckets_cents": buckets_cents,
        "items": details,
    }
