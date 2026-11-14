# -*- coding: utf-8 -*-
"""多云算力底座成本（阿里云 GPU 推理集群 / 腾讯云对象存储 / BGP 带宽）按租户调用当量分摊与毛利率核算引擎。"""
import sqlite3
from typing import Any, Dict, List

from app.infra.db import parse_legacy_amount_cents


DEFAULT_MONTHLY_INFRA_POOL_CENTS: Dict[str, int] = {
    "GPU_INFERENCE_CLUSTER": 680_000,   # ¥6,800.00
    "K8S_GENERAL_COMPUTE": 290_000,     # ¥2,900.00
    "RDS_AND_OBJECT_STORAGE": 140_000,  # ¥1,400.00
    "BGP_EGRESS_BANDWIDTH": 90_000,     # ¥900.00
}


def compute_period_tenant_gross_margins(
    conn: sqlite3.Connection,
    period_key: str = "2026-11",
    infra_pool_override: Dict[str, int] = None,
) -> Dict[str, Any]:
    """按当期各租户有效调用总量占比分摊可变算力成本，并结合不含税账单收入计算单租户毛利额与毛利率。"""
    pool = dict(infra_pool_override or DEFAULT_MONTHLY_INFRA_POOL_CENTS)
    total_cogs_cents = sum(max(0, int(v)) for v in pool.values())

    usage_rows = conn.execute(
        """
        SELECT tenant_id, COALESCE(SUM(total_quantity), 0) AS qty
        FROM usage_summaries
        WHERE period_key = ?
        GROUP BY tenant_id
        """,
        (period_key,),
    ).fetchall()
    qty_by_tenant = {str(r["tenant_id"]): int(r["qty"] or 0) for r in usage_rows}
    platform_total_qty = max(1, sum(qty_by_tenant.values()))

    inv_rows = conn.execute(
        "SELECT * FROM invoices WHERE period_key = ? AND status != 'VOID'",
        (period_key,),
    ).fetchall()
    net_rev_by_tenant: Dict[str, int] = {}
    for r in inv_rows:
        d = dict(r)
        tid = str(d["tenant_id"])
        gross = parse_legacy_amount_cents(d, "total_cents")
        tax = int(d.get("tax_cents") or 0)
        net_rev_by_tenant[tid] = net_rev_by_tenant.get(tid, 0) + max(0, gross - tax)

    all_tids = sorted(set(qty_by_tenant.keys()) | set(net_rev_by_tenant.keys()))
    tenant_margins: List[Dict[str, Any]] = []
    negative_margin_count = 0

    for tid in all_tids:
        t_qty = qty_by_tenant.get(tid, 0)
        allocated_cogs = int(round((total_cogs_cents * t_qty) / float(platform_total_qty)))
        net_rev = net_rev_by_tenant.get(tid, 0)
        gross_profit = net_rev - allocated_cogs
        if gross_profit < 0:
            negative_margin_count += 1
        gm_bps = int((gross_profit * 10000) // net_rev) if net_rev > 0 else (-10000 if allocated_cogs > 0 else 0)
        tenant_margins.append({
            "tenant_id": tid,
            "usage_quantity": t_qty,
            "net_revenue_cents": net_rev,
            "allocated_cogs_cents": allocated_cogs,
            "gross_profit_cents": gross_profit,
            "gross_margin_bps": gm_bps,
        })

    total_net_rev = sum(net_rev_by_tenant.values())
    platform_gp = total_net_rev - total_cogs_cents
    platform_gm_bps = int((platform_gp * 10000) // max(1, total_net_rev))
    return {
        "period_key": period_key,
        "total_infra_cogs_cents": total_cogs_cents,
        "total_net_revenue_cents": total_net_rev,
        "platform_gross_profit_cents": platform_gp,
        "platform_gross_margin_bps": platform_gm_bps,
        "negative_margin_tenant_count": negative_margin_count,
        "tenants": tenant_margins,
    }
