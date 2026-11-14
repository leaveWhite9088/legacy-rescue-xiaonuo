# -*- coding: utf-8 -*-
"""[历史迁移脚本 2025-06] 渠道伙伴返佣等级按季度实收净现金重评定批处理（离线脚本）。"""
import sqlite3
from typing import Any, Dict, List

from app.infra.config import PARTNER_TIERS


def evaluate_partner_tier_upgrades_dryrun(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT partner_code, SUM(net_cash_collected_cents) AS q_cash
        FROM partner_commissions
        GROUP BY partner_code
        ORDER BY partner_code ASC
        """
    ).fetchall()
    proposals: List[Dict[str, Any]] = []
    for r in rows:
        q_cash = int(r["q_cash"] or 0)
        suggested = "SILVER"
        if q_cash >= PARTNER_TIERS["PLATINUM"]["min_quarterly_cents"]:
            suggested = "PLATINUM"
        elif q_cash >= PARTNER_TIERS["GOLD"]["min_quarterly_cents"]:
            suggested = "GOLD"
        proposals.append({
            "partner_code": r["partner_code"],
            "cumulative_net_cash_cents": q_cash,
            "suggested_tier": suggested,
        })
    return proposals
