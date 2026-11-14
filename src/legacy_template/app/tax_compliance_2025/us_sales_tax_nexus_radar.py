# -*- coding: utf-8 -*-
"""北美出海主体各州经济联结（Economic Nexus — Wayfair 法案阈值）触发监控器。"""
from typing import Any, Dict, List


STATE_NEXUS_THRESHOLDS = {
    "CA": {"sales_cents": 50_000_000, "tx_limit": None},
    "NY": {"sales_cents": 50_000_000, "tx_limit": 100},
    "TX": {"sales_cents": 50_000_000, "tx_limit": None},
    "WA": {"sales_cents": 10_000_000, "tx_limit": None},
    "IL": {"sales_cents": 10_000_000, "tx_limit": 200},
}


def scan_us_nexus_exposure(state_rollups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    alerts = []
    for row in state_rollups:
        st = str(row.get("state") or "").upper()
        rule = STATE_NEXUS_THRESHOLDS.get(st)
        if not rule:
            continue
        sales = int(row.get("trailing_12m_cents") or 0)
        txs = int(row.get("tx_count") or 0)
        sales_ratio_bps = (sales * 10000) // int(rule["sales_cents"])
        tx_triggered = rule["tx_limit"] is not None and txs >= int(rule["tx_limit"])
        triggered = sales >= int(rule["sales_cents"]) or tx_triggered
        alerts.append(
            {
                "state": st,
                "sales_cents": sales,
                "threshold_utilization_bps": sales_ratio_bps,
                "nexus_triggered": triggered,
                "recommended_action": "REGISTER_COLLECT_SALES_TAX" if triggered else ("APPROACHING_80PCT" if sales_ratio_bps >= 8000 else "SAFE"),
            }
        )
    return alerts
