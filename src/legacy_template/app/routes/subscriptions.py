# -*- coding: utf-8 -*-
"""订阅查询、套餐变更、到期退订与手动续期路由（经由 portal_facade 编排）。"""
from datetime import datetime, timezone
from flask import Blueprint, current_app, g, jsonify, request

from app.facades.portal_facade import (
    execute_portal_cancel,
    execute_portal_manual_renew,
    execute_portal_plan_change,
    load_portal_dashboard_bundle,
    load_portal_subscription_view,
)
from app.infra.db import tx_context
from app.routes.auth import require_tenant

bp = Blueprint("subscriptions", __name__, url_prefix="/api/subscriptions")


@bp.route("/current", methods=["GET"])
@require_tenant
def get_current_subscription():
    db_path = current_app.config.get("DB_PATH")
    period_key = request.args.get("period_key") or datetime.now(timezone.utc).strftime("%Y-%m")
    try:
        with tx_context(db_path) as conn:
            return jsonify(load_portal_subscription_view(conn, g.tenant["id"], period_key))
    except LookupError as e:
        return jsonify({"error": str(e)}), 404


@bp.route("/dashboard-bundle", methods=["GET"])
@require_tenant
def get_portal_bundle():
    db_path = current_app.config.get("DB_PATH")
    period_key = request.args.get("period_key") or datetime.now(timezone.utc).strftime("%Y-%m")
    try:
        with tx_context(db_path) as conn:
            return jsonify(load_portal_dashboard_bundle(conn, g.tenant["id"], period_key))
    except LookupError as e:
        return jsonify({"error": str(e)}), 404


@bp.route("/change-plan", methods=["POST"])
@require_tenant
def change_plan():
    data = request.get_json(silent=True) or {}
    new_plan = str(data.get("plan_code", "")).strip()
    reason = str(data.get("reason", "tenant_change"))
    db_path = current_app.config.get("DB_PATH")
    try:
        with tx_context(db_path, immediate=True) as conn:
            res = execute_portal_plan_change(conn, g.tenant["id"], new_plan, reason=reason)
        return jsonify(res)
    except LookupError as e:
        return jsonify({"error": str(e)}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/cancel", methods=["POST"])
@require_tenant
def cancel_subscription():
    db_path = current_app.config.get("DB_PATH")
    try:
        with tx_context(db_path, immediate=True) as conn:
            res = execute_portal_cancel(conn, g.tenant["id"])
        return jsonify(res)
    except LookupError as e:
        return jsonify({"error": str(e)}), 404


@bp.route("/renew", methods=["POST"])
@require_tenant
def manual_renew():
    db_path = current_app.config.get("DB_PATH")
    try:
        with tx_context(db_path, immediate=True) as conn:
            res = execute_portal_manual_renew(conn, g.tenant["id"])
        return jsonify(res), 201
    except LookupError as e:
        return jsonify({"error": str(e)}), 404
