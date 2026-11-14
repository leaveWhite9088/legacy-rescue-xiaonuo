# -*- coding: utf-8 -*-
"""v3 影子账单比对器（由中间件或后台巡检以只读方式采样调用，不修改任何业务表）。"""
import sqlite3
from typing import Any, Dict, List

from app.v3_pipeline.commands import ComputeCycleTariffCommand, UsageSegmentWindow
from app.v3_pipeline.segmented_pricer import SegmentedTariffEngineV3


def run_shadow_tariff_diff_sample(conn: sqlite3.Connection, period_key: str, sample_limit: int = 15) -> Dict[str, Any]:
    """抽样对比数据库账单总额与 v3 实验计价器估算结果（自动跳过老租户与特殊税率租户）。"""
    rows = conn.execute(
        """
        SELECT i.id, i.tenant_id, i.plan_code, i.total_cents, t.schema_version, t.tax_profile_code
        FROM invoices i
        JOIN tenants t ON t.id = i.tenant_id
        WHERE i.period_key = ? AND i.status != 'VOID'
        ORDER BY i.id ASC
        LIMIT ?
        """,
        (period_key, sample_limit),
    ).fetchall()

    engine = SegmentedTariffEngineV3()
    compared = 0
    skipped = 0
    divergences: List[Dict[str, Any]] = []

    for inv in rows:
        if int(inv["schema_version"] or 2) == 1 or inv["tax_profile_code"] != "CN_VAT_6_INCLUSIVE":
            skipped += 1
            continue
        segs_raw = conn.execute(
            "SELECT plan_code, total_quantity FROM usage_summaries WHERE tenant_id = ? AND period_key = ?",
            (inv["tenant_id"], period_key),
        ).fetchall()
        segs = tuple(
            UsageSegmentWindow(
                tenant_id=inv["tenant_id"],
                period_key=period_key,
                plan_code=s["plan_code"],
                window_start_iso=f"{period_key}-01T00:00:00Z",
                window_end_iso=f"{period_key}-28T23:59:59Z",
                quantity=int(s["total_quantity"]),
            )
            for s in segs_raw
        )
        try:
            est = engine.execute(
                ComputeCycleTariffCommand(
                    tenant_id=inv["tenant_id"],
                    period_key=period_key,
                    closing_plan_code=inv["plan_code"],
                    segments=segs,
                )
            )
            compared += 1
            if est["total_cents"] != int(inv["total_cents"]):
                divergences.append({
                    "invoice_id": inv["id"],
                    "tenant_id": inv["tenant_id"],
                    "v2_cents": int(inv["total_cents"]),
                    "v3_shadow_cents": est["total_cents"],
                })
        except NotImplementedError:
            skipped += 1

    return {
        "period_key": period_key,
        "compared_count": compared,
        "skipped_count": skipped,
        "divergence_count": len(divergences),
        "divergences": divergences,
    }
