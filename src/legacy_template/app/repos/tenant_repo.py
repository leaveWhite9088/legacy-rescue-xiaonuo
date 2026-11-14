# -*- coding: utf-8 -*-
"""租户、税率档案与企业大客户合同仓储。"""
import sqlite3
from typing import Any, Dict, List, Optional

from app.infra.cache import contract_cache
from app.infra.db import normalize_tenant_record


def get_tenant_by_id(conn: sqlite3.Connection, tenant_id: str) -> Optional[Dict[str, Any]]:
    row = conn.execute("SELECT * FROM tenants WHERE id = ?", (tenant_id,)).fetchone()
    return normalize_tenant_record(row) if row else None


def get_tenant_by_token(conn: sqlite3.Connection, token: str) -> Optional[Dict[str, Any]]:
    row = conn.execute("SELECT * FROM tenants WHERE api_token = ?", (token,)).fetchone()
    return normalize_tenant_record(row) if row else None


def get_active_enterprise_contract(conn: sqlite3.Connection, tenant_id: str) -> Optional[Dict[str, Any]]:
    ck = f"contract:{tenant_id}"
    cached = contract_cache.get(ck)
    if cached is not None:
        return cached
    row = conn.execute(
        "SELECT * FROM enterprise_contracts WHERE tenant_id = ? AND status = 'ACTIVE' LIMIT 1",
        (tenant_id,),
    ).fetchone()
    res = dict(row) if row else None
    if res is not None:
        contract_cache.set(ck, res)
    return res


def list_all_tenants_overview(conn: sqlite3.Connection, limit: int = 200) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT t.*, w.cash_balance_cents, w.promo_balance_cents, s.plan_code, s.status AS sub_status
        FROM tenants t
        LEFT JOIN wallets w ON w.tenant_id = t.id
        LEFT JOIN subscriptions s ON s.tenant_id = t.id
        ORDER BY t.created_at ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    out = []
    for r in rows:
        d = normalize_tenant_record(r)
        d.pop("api_token", None)
        out.append(d)
    return out
