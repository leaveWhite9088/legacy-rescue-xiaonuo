# -*- coding: utf-8 -*-
"""年度财务审计外审资料包（PBC Package）目录清单与 SHA-256 完整性指纹生成器。"""
import hashlib
import json
import sqlite3
from typing import Any, Dict

from app.finance_recon_hub.deferred_revenue_rollforward import compute_cash_wallet_rollforward
from app.finance_recon_hub.promo_liability_rollforward import compute_promo_wallet_rollforward
from app.finance_recon_hub.three_way_cdr_bill_gl import build_period_three_way_tieout


def build_pbc_workpaper_bundle(conn: sqlite3.Connection, target_period: str = "2026-11") -> Dict[str, Any]:
    tieout = build_period_three_way_tieout(conn, target_period)
    cash_rf = compute_cash_wallet_rollforward(conn)
    promo_rf = compute_promo_wallet_rollforward(conn)

    payload = {
        "pbc_version": "FY2026-Q4-REV1",
        "target_period": target_period,
        "schedule_A_three_way_tieout": tieout,
        "schedule_B_deferred_cash_rollforward": cash_rf,
        "schedule_C_promo_credits_rollforward": promo_rf,
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return {
        "bundle_sha256": digest,
        "workpapers": payload,
    }
