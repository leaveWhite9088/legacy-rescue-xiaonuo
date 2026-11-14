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
