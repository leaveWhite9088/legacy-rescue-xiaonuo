# -*- coding: utf-8 -*-
"""钱包余额、充值与赠送金发放接口。"""
from flask import Blueprint, current_app, g, jsonify, request

from app.domain.ledger import get_wallet, grant_promo_credit, topup_cash
from app.infra.db import tx_context
from app.routes.auth import require_admin, require_tenant

bp = Blueprint("wallet", __name__, url_prefix="/api/wallet")


@bp.route("", methods=["GET"])
@require_tenant
def read_wallet():
    db_path = current_app.config.get("DB_PATH")
    with tx_context(db_path) as conn:
        w = get_wallet(conn, g.tenant["id"])
        ledger = conn.execute(
            "SELECT * FROM wallet_ledger WHERE tenant_id = ? ORDER BY id DESC LIMIT 20",
            (g.tenant["id"],),
        ).fetchall()
    return jsonify({"wallet": w, "recent_ledger": [dict(x) for x in ledger]})


@bp.route("/topup", methods=["POST"])
@require_tenant
def wallet_topup():
    data = request.get_json(silent=True) or {}
    try:
        amount_cents = int(data["amount_cents"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "amount_cents 必须为整数"}), 400
    db_path = current_app.config.get("DB_PATH")
    try:
        with tx_context(db_path, immediate=True) as conn:
            w = topup_cash(conn, g.tenant["id"], amount_cents, ref_id=str(data.get("ref_id", "")))
        return jsonify({"wallet": w})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/promo-grant", methods=["POST"])
@require_admin
def admin_grant_promo():
    data = request.get_json(silent=True) or {}
    tenant_id = str(data.get("tenant_id", "")).strip()
    expires_at = str(data.get("expires_at", "")).strip()
    try:
        amount_cents = int(data["amount_cents"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "amount_cents 必须为整数"}), 400
    if not tenant_id or not expires_at:
        return jsonify({"error": "缺少 tenant_id 或 expires_at"}), 400
    db_path = current_app.config.get("DB_PATH")
    try:
        with tx_context(db_path, immediate=True) as conn:
            res = grant_promo_credit(conn, tenant_id, amount_cents, expires_at)
        return jsonify(res), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
