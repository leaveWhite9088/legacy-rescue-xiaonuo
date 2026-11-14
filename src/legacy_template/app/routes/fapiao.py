# -*- coding: utf-8 -*-
"""数电增值税发票申请、查询与红字冲销接口。"""
from flask import Blueprint, current_app, g, jsonify, request

from app.infra.db import tx_context
from app.routes.auth import require_admin, require_tenant
from app.services.fapiao_service import (
    get_tenant_fapiao_list,
    issue_red_letter_fapiao,
    request_vat_fapiao_for_invoice,
)

bp = Blueprint("fapiao", __name__, url_prefix="/api/fapiao")


@bp.route("", methods=["GET"])
@require_tenant
def list_my_fapiaos():
    db_path = current_app.config.get("DB_PATH")
    with tx_context(db_path) as conn:
        items = get_tenant_fapiao_list(conn, g.tenant["id"])
    return jsonify({"fapiaos": items})


@bp.route("/apply", methods=["POST"])
@require_tenant
def apply_fapiao():
    data = request.get_json(silent=True) or {}
    invoice_id = str(data.get("invoice_id", "")).strip()
    buyer_tax_id = str(data.get("buyer_tax_id", "")).strip()
    fapiao_type = str(data.get("fapiao_type", "VAT_SPECIAL_E")).strip()
    if not invoice_id or not buyer_tax_id:
        return jsonify({"error": "缺少 invoice_id 或 buyer_tax_id"}), 400
    db_path = current_app.config.get("DB_PATH")
    try:
        with tx_context(db_path, immediate=True) as conn:
            res = request_vat_fapiao_for_invoice(
                conn,
                tenant_id=g.tenant["id"],
                invoice_id=invoice_id,
                buyer_tax_id=buyer_tax_id,
                fapiao_type=fapiao_type,
            )
        return jsonify(res), 201
    except LookupError as e:
        return jsonify({"error": str(e)}), 404
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/<fapiao_id>/red-letter", methods=["POST"])
@require_admin
def admin_red_reverse(fapiao_id: str):
    db_path = current_app.config.get("DB_PATH")
    try:
        with tx_context(db_path, immediate=True) as conn:
            res = issue_red_letter_fapiao(conn, fapiao_id, operator="admin_api")
        return jsonify(res)
    except LookupError as e:
        return jsonify({"error": str(e)}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
