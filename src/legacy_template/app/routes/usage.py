# -*- coding: utf-8 -*-
"""计量事件上报与配额使用汇总查询路由（经由 metering_facade 编排）。"""
from datetime import datetime, timezone
from flask import Blueprint, current_app, g, jsonify, request

from app.facades.metering_facade import facade_get_usage_summary, facade_ingest_usage
from app.infra.db import tx_context
from app.routes.auth import require_tenant

bp = Blueprint("usage", __name__, url_prefix="/api/usage")


@bp.route("/events", methods=["POST"])
@require_tenant
def ingest_usage_event():
    data = request.get_json(silent=True) or {}
    if "quantity" not in data:
        return jsonify({"error": "缺少 quantity 字段"}), 400

    db_path = current_app.config.get("DB_PATH")
    try:
        with tx_context(db_path, immediate=True) as conn:
            res = facade_ingest_usage(conn, tenant_id=g.tenant["id"], payload=data)
        return jsonify(res), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 429


@bp.route("/summary", methods=["GET"])
@require_tenant
def get_usage_summary():
    period_key = request.args.get("period_key") or datetime.now(timezone.utc).strftime("%Y-%m")
    db_path = current_app.config.get("DB_PATH")
    with tx_context(db_path) as conn:
        snap = facade_get_usage_summary(conn, g.tenant["id"], period_key)
    return jsonify(snap)
