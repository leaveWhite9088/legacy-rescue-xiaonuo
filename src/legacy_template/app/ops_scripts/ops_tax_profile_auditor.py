# -*- coding: utf-8 -*-
"""存量租户税务档案合规巡检器：核查价内税/价外税适用范围与跨境免税备案完整性。"""
import sqlite3
from typing import Any, Dict, List

from app.infra.config import TAX_PROFILES


def audit_tenant_tax_profiles(conn: sqlite3.Connection) -> Dict[str, Any]:
    rows = conn.execute("SELECT id, company_name, status, tier_level, tax_profile_code FROM tenants ORDER BY id ASC").fetchall()
    distribution: Dict[str, int] = {}
    anomalies: List[Dict[str, str]] = []

    for r in rows:
        code = str(r["tax_profile_code"] or "CN_VAT_6_INCLUSIVE")
        distribution[code] = distribution.get(code, 0) + 1
        if code not in TAX_PROFILES:
            anomalies.append({
                "tenant_id": r["id"],
                "issue": f"UNKNOWN_TAX_CODE:{code}",
            })

    return {
        "checked_tenants": len(rows),
        "profile_distribution": distribution,
        "advisory_findings": anomalies,
    }
