# -*- coding: utf-8 -*-
"""收入保障（Revenue Assurance）漏收防线静态巡检器：检查活跃订阅是否漏配税码、企业保底合同是否过低配置。"""
import sqlite3
from typing import Any, Dict, List

from app.infra.config import PLANS


def check_revenue_leakage_risks(conn: sqlite3.Connection) -> Dict[str, Any]:
    contracts = conn.execute(
        """
        SELECT c.*, s.plan_code
        FROM enterprise_contracts c
        LEFT JOIN subscriptions s ON s.tenant_id = c.tenant_id
        """
    ).fetchall()

    under_floor_contracts: List[Dict[str, Any]] = []
    for c in contracts:
        p_code = str(c["plan_code"] or "ENTERPRISE")
        std_fee = int(PLANS.get(p_code, PLANS["ENTERPRISE"])["monthly_fee_cents"])
        min_commit = int(c["min_monthly_commit_cents"] or 0)
        disc_bps = int(c["custom_overage_discount_bps"] or 0)
        # 若超额折扣大于 20% 但最低保底还低于标准套餐月租，提示商务倒挂风险
        if disc_bps >= 2000 and min_commit < std_fee:
            under_floor_contracts.append({
                "contract_id": c["id"],
                "tenant_id": c["tenant_id"],
                "plan_code": p_code,
                "min_commit_cents": min_commit,
                "standard_monthly_cents": std_fee,
                "discount_bps": disc_bps,
            })

    return {
        "checked_contracts": len(contracts),
        "margin_inversion_warnings": under_floor_contracts,
    }
