# -*- coding: utf-8 -*-
"""租户双资金池头寸与活跃赠送金批次点位快照导出器（供日终离线备份与外审函证抽样）。"""
import json
import sqlite3
from typing import Any, Dict, List


def dump_point_in_time_wallet_snapshot(conn: sqlite3.Connection) -> Dict[str, Any]:
    rows = conn.execute(
        """
        SELECT w.tenant_id, t.company_name, t.status AS tenant_status,
               w.cash_balance_cents, w.promo_balance_cents, w.updated_at
        FROM wallets w
        JOIN tenants t ON t.id = w.tenant_id
        ORDER BY w.tenant_id ASC
        """
    ).fetchall()

    grants = conn.execute(
        """
        SELECT tenant_id, status, COUNT(*) AS batch_cnt, COALESCE(SUM(remaining_cents), 0) AS rem_sum
        FROM promo_grants
        GROUP BY tenant_id, status
        """
    ).fetchall()

    grant_map: Dict[str, Dict[str, int]] = {}
    for g in grants:
        tid = g["tenant_id"]
        st = g["status"]
        grant_map.setdefault(tid, {})[st] = int(g["rem_sum"] or 0)

    records: List[Dict[str, Any]] = []
    sum_cash = 0
    sum_promo = 0
    for r in rows:
        tid = r["tenant_id"]
        c_bal = int(r["cash_balance_cents"] or 0)
        p_bal = int(r["promo_balance_cents"] or 0)
        sum_cash += c_bal
        sum_promo += p_bal
        records.append({
            "tenant_id": tid,
            "company_name": r["company_name"],
            "tenant_status": r["tenant_status"],
            "cash_balance_cents": c_bal,
            "promo_balance_cents": p_bal,
            "active_grant_remaining_cents": grant_map.get(tid, {}).get("ACTIVE", 0),
            "expired_grant_remaining_cents": grant_map.get(tid, {}).get("EXPIRED", 0),
        })

    return {
        "tenant_count": len(records),
        "aggregate_cash_balance_cents": sum_cash,
        "aggregate_promo_balance_cents": sum_promo,
        "records": records,
    }


def serialize_wallet_snapshot_jsonl(conn: sqlite3.Connection) -> str:
    snap = dump_point_in_time_wallet_snapshot(conn)
    return "\n".join(json.dumps(rec, ensure_ascii=False) for rec in snap["records"])
