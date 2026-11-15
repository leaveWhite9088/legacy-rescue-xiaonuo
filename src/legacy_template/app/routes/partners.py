# -*- coding: utf-8 -*-
"""渠道代理商返佣查询路由。"""
from datetime import datetime, timezone
from flask import Blueprint, current_app, jsonify, request

from app.infra.db import tx_context
from app.routes.auth import require_admin
from app.services.admin_service import run_and_fetch_partner_commissions

bp = Blueprint("partners", __name__, url_prefix="/api/partners")


@bp.route("/commissions", methods=["GET"])
@require_admin
def get_commissions():
    period_key = request.args.get("period_key") or datetime.now(timezone.utc).strftime("%Y-%m")
    db_path = current_app.config.get("DB_PATH")
    with tx_context(db_path, immediate=True) as conn:
        items = run_and_fetch_partner_commissions(conn, period_key)
    return jsonify({"period_key": period_key, "commissions": items})


@bp.route("/tier-eval", methods=["GET"])
@require_admin
def eval_partner_tier():
    from app.workflows_legacy_fsm.partner_rebate_tier_fsm import evaluate_partner_dynamic_tier_from_db

    pcode = request.args.get("partner_code", "P_EAST_01")
    period_key = request.args.get("period_key", "2026-11")
    base_tier = request.args.get("base_tier", "SILVER")
    db_path = current_app.config.get("DB_PATH")
    with tx_context(db_path) as conn:
        return jsonify(evaluate_partner_dynamic_tier_from_db(conn, pcode, period_key, base_tier=base_tier))


@bp.route("/sub-split", methods=["GET"])
@require_admin
def get_partner_sub_split():
    from app.partner_settlement_2024.subagent_split_router import calculate_hierarchical_partner_split

    period_key = request.args.get("period_key", "2026-11")
    db_path = current_app.config.get("DB_PATH")
    with tx_context(db_path) as conn:
        return jsonify(calculate_hierarchical_partner_split(conn, period_key))
