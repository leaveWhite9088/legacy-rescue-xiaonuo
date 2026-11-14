# -*- coding: utf-8 -*-
"""2024 应收账款 (AR) 账龄五级分类与坏账准备金计提（ECL 预期信用损失法）测算脚本。"""
from datetime import datetime
import sqlite3
from typing import Any, Dict, List

from app.infra.db import parse_legacy_amount_cents


ECL_PROVISION_RATES_BPS = (
    (0, 0, 50, "CURRENT_NOT_DUE"),          # 未逾期：0.5% 一般风险准备
    (1, 30, 300, "OVERDUE_1_30_DAYS"),      # 逾期 1~30 天：3.0%
    (31, 60, 1000, "OVERDUE_31_60_DAYS"),   # 逾期 31~60 天：10.0%
    (61, 90, 3500, "OVERDUE_61_90_DAYS"),   # 逾期 61~90 天：35.0%
    (91, 99999, 8000, "OVERDUE_90_PLUS"),   # 逾期 90 天以上：80.0%
)


def _days_between_iso(due_iso: str, as_of_iso: str) -> int:
    try:
        d_due = datetime.fromisoformat(due_iso.replace("Z", "+00:00"))
        d_now = datetime.fromisoformat(as_of_iso.replace("Z", "+00:00"))
        return max(0, (d_now - d_due).days)
    except ValueError:
        return 0


def compute_ecl_bad_debt_provision_2024(
    conn: sqlite3.Connection,
    as_of_iso: str = "2026-11-14T00:00:00Z",
) -> Dict[str, Any]:
    """遍历全部未结清账单，按预期信用损失模型（ECL）分桶计提坏账准备。"""
    rows = conn.execute(
        "SELECT * FROM invoices WHERE status IN ('OPEN', 'PAST_DUE', 'DISPUTED', 'PENDING_SETTLE') ORDER BY id ASC"
    ).fetchall()

    buckets: Dict[str, Dict[str, int]] = {
        label: {"invoice_count": 0, "unpaid_principal_cents": 0, "provision_cents": 0, "rate_bps": rate}
        for _, _, rate, label in ECL_PROVISION_RATES_BPS
    }

    total_ar = 0
    total_prov = 0
    for r in rows:
        d = dict(r)
        tot = parse_legacy_amount_cents(d, "total_cents")
        paid = parse_legacy_amount_cents(d, "paid_cents")
        unpaid = max(0, tot - paid)
        if unpaid <= 0:
            continue

        overdue_days = _days_between_iso(str(d.get("due_at") or as_of_iso), as_of_iso)
        matched_label = "CURRENT_NOT_DUE"
        matched_rate = 50
        for lo, hi, rate, label in ECL_PROVISION_RATES_BPS:
            if lo <= overdue_days <= hi:
                matched_label = label
                matched_rate = rate
                break

        prov = (unpaid * matched_rate) // 10000
        b = buckets[matched_label]
        b["invoice_count"] += 1
        b["unpaid_principal_cents"] += unpaid
        b["provision_cents"] += prov
        total_ar += unpaid
        total_prov += prov

    return {
        "as_of": as_of_iso,
        "total_open_ar_cents": total_ar,
        "total_ecl_provision_cents": total_prov,
        "effective_coverage_bps": int((total_prov * 10000) // max(1, total_ar)),
        "aging_buckets": buckets,
    }
