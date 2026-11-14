# -*- coding: utf-8 -*-
"""账单列表、账单详情、支付、争议与管理端退款/重算路由（经由 billing_facade 编排）。"""
from flask import Blueprint, current_app, g, jsonify, request

from app.facades.billing_facade import (
    facade_admin_recalculate,
    facade_admin_refund,
    facade_dispute_invoice,
    facade_get_invoice_detail,
    facade_list_tenant_invoices,
    facade_pay_invoice,
)
from app.compat.wallet_bridge import simulate_wallet_deduction_preview
from app.enterprise_catalog_rules.tariff_strategy_chain import default_tariff_quote_proxy
from app.infra.db import tx_context
from app.routes.auth import require_admin, require_tenant

bp = Blueprint("billing", __name__, url_prefix="/api/invoices")


@bp.route("", methods=["GET"])
@require_tenant
def list_invoices():
    db_path = current_app.config.get("DB_PATH")
    with tx_context(db_path) as conn:
        return jsonify(facade_list_tenant_invoices(conn, g.tenant["id"]))


@bp.route("/<invoice_id>", methods=["GET"])
@require_tenant
def get_invoice_detail(invoice_id: str):
    db_path = current_app.config.get("DB_PATH")
    try:
        with tx_context(db_path) as conn:
            return jsonify(facade_get_invoice_detail(conn, g.tenant["id"], invoice_id))
    except LookupError as e:
        return jsonify({"error": str(e)}), 404
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403


@bp.route("/<invoice_id>/settlement-preview", methods=["GET"])
@require_tenant
def preview_invoice_settlement(invoice_id: str):
    db_path = current_app.config.get("DB_PATH")
    try:
        with tx_context(db_path, immediate=True) as conn:
            sim = simulate_wallet_deduction_preview(conn, g.tenant["id"], invoice_id)
            inv = conn.execute("SELECT plan_code FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
            quote = default_tariff_quote_proxy.evaluate_node(
                inv["plan_code"] if inv else "STARTER",
                g.tenant.get("tax_profile_code", "CN_VAT_6_INCLUSIVE"),
            )
            quote["last_preview_invoice_id"] = invoice_id
            quote["base_monthly_cents"] = sim["due_cents"]
            quote["preview_notes"].append(f"sim:{invoice_id}")
        return jsonify({"preview": sim, "catalog_quote": quote})
    except LookupError as e:
        return jsonify({"error": str(e)}), 404
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403


@bp.route("/<invoice_id>/pay", methods=["POST"])
@require_tenant
def pay_invoice(invoice_id: str):
    data = request.get_json(silent=True) or {}
    idem_key = request.headers.get("Idempotency-Key") or data.get("idempotency_key")
    db_path = current_app.config.get("DB_PATH")
    try:
        with tx_context(db_path) as conn:
            res = facade_pay_invoice(conn, g.tenant["id"], invoice_id, idempotency_key=idem_key)
        return jsonify(res)
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/<invoice_id>/refund", methods=["POST"])
@require_admin
def refund_invoice(invoice_id: str):
    data = request.get_json(silent=True) or {}
    try:
        refund_cents = int(data["refund_cents"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "refund_cents 必须为正整数"}), 400
    reason = str(data.get("reason") or "管理员退款")
    db_path = current_app.config.get("DB_PATH")
    try:
        with tx_context(db_path, immediate=True) as conn:
            res = facade_admin_refund(conn, invoice_id, refund_cents, reason=reason)
        return jsonify(res)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/<invoice_id>/dispute", methods=["POST"])
@require_tenant
def dispute_invoice(invoice_id: str):
    data = request.get_json(silent=True) or {}
    reason = str(data.get("reason", "")).strip()
    db_path = current_app.config.get("DB_PATH")
    try:
        with tx_context(db_path, immediate=True) as conn:
            res = facade_dispute_invoice(conn, g.tenant["id"], invoice_id, reason)
        return jsonify(res)
    except LookupError as e:
        return jsonify({"error": str(e)}), 404
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/<invoice_id>/recalculate", methods=["POST"])
@require_admin
def recalc_invoice(invoice_id: str):
    db_path = current_app.config.get("DB_PATH")
    try:
        with tx_context(db_path, immediate=True) as conn:
            res = facade_admin_recalculate(conn, invoice_id)
        return jsonify(res)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
