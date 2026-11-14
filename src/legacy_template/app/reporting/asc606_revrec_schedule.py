# -*- coding: utf-8 -*-
"""新收入准则 (CAS 14 / IFRS 15 / ASC 606) 权责发生制递延收入每日摊销底稿生成器。
会计规则：
1. 基础订阅费（含最低保底补足额）在服务周期 [cycle_start, cycle_end) 内按自然日等额确认收入，剩余未到期部分列报为合同负债；
2. 阶梯超额计量费属于可变对价，在当月实际发生且金额确定时于当期全额确认；
3. 价外增值税销项税额不计入主营业务收入净额。
"""
from datetime import datetime, timedelta, timezone
import sqlite3
from typing import Any, Dict, List

from app.infra.config import TAX_PROFILES
from app.infra.db import parse_legacy_amount_cents
from app.utils.calc_helpers import allocate_pro_rata_cents


def _parse_utc_date(iso_str: str) -> datetime:
    s = (iso_str or "").strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return datetime(2026, 11, 1, tzinfo=timezone.utc)


def _strip_inclusive_vat(gross_cents: int, tax_profile_code: str) -> int:
    tp = TAX_PROFILES.get(tax_profile_code, TAX_PROFILES["CN_VAT_6_INCLUSIVE"])
    rate_bps = int(tp["rate_bps"])
    if not tp["inclusive"] or rate_bps <= 0:
        return int(gross_cents)
    return int(round(int(gross_cents) * 10000.0 / (10000 + rate_bps)))


def build_invoice_revrec_waterfall(inv_dict: Dict[str, Any], tax_profile_code: str, cutoff_iso: str) -> Dict[str, Any]:
    start_dt = _parse_utc_date(str(inv_dict["cycle_start"]))
    end_dt = _parse_utc_date(str(inv_dict["cycle_end"]))
    cutoff_dt = _parse_utc_date(cutoff_iso)

    total_days = max(1, (end_dt.date() - start_dt.date()).days)
    elapsed_days = max(0, min(total_days, (cutoff_dt.date() - start_dt.date()).days))

    if inv_dict.get("currency_unit") == "YUAN_STR":
        gross_base = parse_legacy_amount_cents(inv_dict, "total_cents")
        gross_overage = 0
    else:
        gross_base = int(inv_dict.get("base_fee_cents") or 0)
        gross_overage = int(inv_dict.get("overage_fee_cents") or 0)

    net_base = _strip_inclusive_vat(gross_base, tax_profile_code)
    net_overage = _strip_inclusive_vat(gross_overage, tax_profile_code)

    daily_shares = allocate_pro_rata_cents(net_base, [1] * total_days)
    recognized_base = sum(daily_shares[:elapsed_days])
    deferred_base = net_base - recognized_base

    # 可变超额对价在账单出具期确认
    recognized_overage = net_overage if cutoff_dt >= start_dt else 0
    return {
        "invoice_id": inv_dict["id"],
        "tenant_id": inv_dict["tenant_id"],
        "service_days_total": total_days,
        "service_days_elapsed": elapsed_days,
        "net_base_cents": net_base,
        "net_overage_cents": net_overage,
        "recognized_revenue_cents": recognized_base + recognized_overage,
        "deferred_revenue_liability_cents": deferred_base,
    }


def generate_period_asc606_schedule(
    conn: sqlite3.Connection,
    period_key: str,
    cutoff_iso: str = "2026-11-15T00:00:00Z",
) -> Dict[str, Any]:
    rows = conn.execute(
        """
        SELECT i.*, t.tax_profile_code, t.company_name
        FROM invoices i
        JOIN tenants t ON t.id = i.tenant_id
        WHERE i.period_key = ? AND i.status != 'VOID'
        ORDER BY i.id ASC
        """,
        (period_key,),
    ).fetchall()

    schedules: List[Dict[str, Any]] = []
    rec_sum = 0
    def_sum = 0
    for r in rows:
        d = dict(r)
        wf = build_invoice_revrec_waterfall(d, d.get("tax_profile_code") or "CN_VAT_6_INCLUSIVE", cutoff_iso)
        wf["company_name"] = d["company_name"]
        schedules.append(wf)
        rec_sum += wf["recognized_revenue_cents"]
        def_sum += wf["deferred_revenue_liability_cents"]

    return {
        "period_key": period_key,
        "cutoff_iso": cutoff_iso,
        "invoice_count": len(schedules),
        "total_recognized_net_cents": rec_sum,
        "total_deferred_liability_cents": def_sum,
        "schedules": schedules,
    }
