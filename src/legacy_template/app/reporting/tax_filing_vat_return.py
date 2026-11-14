# -*- coding: utf-8 -*-
"""增值税一般纳税人月度销项税额申报汇总表（含 6% 含税价拆分、6% 价外税、跨境免税及开票未开票调节表）。"""
import sqlite3
from typing import Any, Dict

from app.infra.config import TAX_PROFILES
from app.infra.db import parse_legacy_amount_cents


def generate_vat_filing_workpaper(conn: sqlite3.Connection, period_key: str) -> Dict[str, Any]:
    invs = conn.execute(
        """
        SELECT i.*, t.tax_profile_code
        FROM invoices i
        JOIN tenants t ON t.id = i.tenant_id
        WHERE i.period_key = ? AND i.status != 'VOID'
        """,
        (period_key,),
    ).fetchall()

    buckets: Dict[str, Dict[str, int]] = {
        code: {"invoice_count": 0, "gross_cents": 0, "net_taxable_cents": 0, "output_vat_cents": 0}
        for code in TAX_PROFILES
    }

    for r in invs:
        d = dict(r)
        t_code = d.get("tax_profile_code") or "CN_VAT_6_INCLUSIVE"
        if t_code not in buckets:
            t_code = "CN_VAT_6_INCLUSIVE"
        tp = TAX_PROFILES[t_code]
        gross = parse_legacy_amount_cents(d, "total_cents")

        if tp["inclusive"]:
            rate_bps = int(tp["rate_bps"])
            if rate_bps > 0:
                net = int(round(gross * 10000.0 / (10000 + rate_bps)))
                vat = gross - net
            else:
                net = gross
                vat = 0
        else:
            vat = int(d.get("tax_cents") or 0)
            net = max(0, gross - vat)

        b = buckets[t_code]
        b["invoice_count"] += 1
        b["gross_cents"] += gross
        b["net_taxable_cents"] += net
        b["output_vat_cents"] += vat

    fp_row = conn.execute(
        """
        SELECT COALESCE(SUM(f.tax_amount_cents), 0) AS invoiced_vat_cents,
               COUNT(*) AS fapiao_cnt
        FROM fapiao_requests f
        JOIN invoices i ON i.id = f.invoice_id
        WHERE i.period_key = ? AND f.status IN ('ISSUED', 'RED_ISSUED')
        """,
        (period_key,),
    ).fetchone()

    invoiced_vat = int(fp_row["invoiced_vat_cents"] or 0) if fp_row else 0
    prc_total_vat = (
        buckets["CN_VAT_6_INCLUSIVE"]["output_vat_cents"]
        + buckets["CN_VAT_6_EXCLUSIVE"]["output_vat_cents"]
    )
    unbilled_vat = prc_total_vat - invoiced_vat

    return {
        "period_key": period_key,
        "by_tax_profile": buckets,
        "prc_total_output_vat_cents": prc_total_vat,
        "fapiao_invoiced_vat_cents": invoiced_vat,
        "unbilled_accrued_vat_cents": unbilled_vat,
        "fapiao_sheet_records": int(fp_row["fapiao_cnt"] or 0) if fp_row else 0,
    }
