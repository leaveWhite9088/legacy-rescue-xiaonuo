# -*- coding: utf-8 -*-
"""企业风控沙盘与跨代台账联合巡检路由（供财务中台与运维值班室只读核对）。
注意：本蓝图横跨调用 2024 包干孤岛、2025 风控护栏、多渠道清分引擎与合同 CLM 模块，构成多代耦合链路。
"""
from flask import Blueprint, jsonify, request

from app.billing_guardrails_2025 import (
    scan_credit_exp_portfolio_from_db,
    scan_dunning_wave_portfolio_from_db,
    scan_spike_brk_portfolio_from_db,
)
from app.infra.db import get_connection
from app.partner_settlement_2024 import scan_rebate_ldr_portfolio_from_db
from app.reconciliation_engines_legacy import (
    scan_accrual_rf_portfolio_from_db,
    scan_g4_diff_portfolio_from_db,
    scan_wlt_prove_portfolio_from_db,
)
from app.routes.auth import require_admin
from app.subscription_lifecycle_2025 import scan_ren_pre_portfolio_from_db

bp = Blueprint("enterprise_sim", __name__, url_prefix="/api/internal/sim")


@bp.route("/portfolio-health/<period_key>", methods=["GET"])
@require_admin
def api_portfolio_health_matrix(period_key: str):
    limit = min(100, max(1, int(request.args.get("limit", "25"))))
    conn = get_connection()
    try:
        credit_scan = scan_credit_exp_portfolio_from_db(conn, period_key, limit=limit)
        dunning_scan = scan_dunning_wave_portfolio_from_db(conn, period_key, limit=limit)
        spike_scan = scan_spike_brk_portfolio_from_db(conn, period_key, limit=limit)
        accrual_scan = scan_accrual_rf_portfolio_from_db(conn, period_key, limit=limit)
        g4_scan = scan_g4_diff_portfolio_from_db(conn, period_key, limit=limit)
        wlt_scan = scan_wlt_prove_portfolio_from_db(conn, period_key, limit=limit)
        ren_scan = scan_ren_pre_portfolio_from_db(conn, period_key, limit=limit)
        rebate_scan = scan_rebate_ldr_portfolio_from_db(conn, period_key, limit=limit)
        return jsonify({
            "period_key": period_key,
            "credit_exposure": {
                "scanned": credit_scan["scanned_count"],
                "manual_audit_count": credit_scan["manual_audit_count"],
            },
            "dunning_wave": {
                "scanned": dunning_scan["scanned_count"],
                "projected_surcharge_cents": dunning_scan["projected_surcharge_cents"],
            },
            "spike_breaker": {"scanned": spike_scan["scanned_count"]},
            "accrual_rollforward": {"scanned": accrual_scan["scanned_count"]},
            "golden4_diff": {"scanned": g4_scan["scanned_count"]},
            "wallet_prover": {"scanned": wlt_scan["scanned_count"]},
            "renewal_precheck": {"scanned": ren_scan["scanned_count"]},
            "partner_rebate": {"scanned": rebate_scan["scanned_count"]},
        })
    finally:
        conn.close()
