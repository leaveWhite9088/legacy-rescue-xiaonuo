# -*- coding: utf-8 -*-
"""月度经常性收入（MRR/ARR）Bridge 瀑布拆解：New / Expansion / Contraction / Churn。"""
import sqlite3
from typing import Any, Dict

from app.infra.db import parse_legacy_amount_cents


def build_period_arr_bridge(
    conn: sqlite3.Connection,
    prev_period: str = "2026-09",
    curr_period: str = "2026-10",
) -> Dict[str, Any]:
    prev_rows = conn.execute(
        "SELECT tenant_id, total_cents, currency_unit, raw_legacy_total FROM invoices WHERE period_key = ? AND status != 'VOID'",
        (prev_period,),
    ).fetchall()
    curr_rows = conn.execute(
        "SELECT tenant_id, total_cents, currency_unit, raw_legacy_total FROM invoices WHERE period_key = ? AND status != 'VOID'",
        (curr_period,),
    ).fetchall()

    prev_map: Dict[str, int] = {}
    for r in prev_rows:
        prev_map[r["tenant_id"]] = prev_map.get(r["tenant_id"], 0) + parse_legacy_amount_cents(dict(r))

    curr_map: Dict[str, int] = {}
    for r in curr_rows:
        curr_map[r["tenant_id"]] = curr_map.get(r["tenant_id"], 0) + parse_legacy_amount_cents(dict(r))

    all_tids = set(prev_map.keys()) | set(curr_map.keys())
    new_mrr = 0
    expansion_mrr = 0
    contraction_mrr = 0
    churn_mrr = 0

    for tid in all_tids:
        p = prev_map.get(tid, 0)
        c = curr_map.get(tid, 0)
        if p == 0 and c > 0:
            new_mrr += c
        elif p > 0 and c == 0:
            churn_mrr += p
        elif c > p:
            expansion_mrr += c - p
        elif c < p:
            contraction_mrr += p - c

    opening_mrr = sum(prev_map.values())
    closing_mrr = sum(curr_map.values())
    nrr_bps = ((closing_mrr - new_mrr) * 10000 // opening_mrr) if opening_mrr > 0 else 10000

    return {
        "prev_period": prev_period,
        "curr_period": curr_period,
        "opening_mrr_cents": opening_mrr,
        "new_mrr_cents": new_mrr,
        "expansion_mrr_cents": expansion_mrr,
        "contraction_mrr_cents": contraction_mrr,
        "churn_mrr_cents": churn_mrr,
        "closing_mrr_cents": closing_mrr,
        "closing_arr_cents": closing_mrr * 12,
        "net_dollar_retention_bps": nrr_bps,
    }
