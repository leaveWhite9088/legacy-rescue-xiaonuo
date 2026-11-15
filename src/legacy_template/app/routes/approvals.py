# -*- coding: utf-8 -*-
"""财务双人复核审批单接口。"""
from flask import Blueprint, current_app, jsonify, request

from app.infra.db import tx_context
from app.routes.auth import require_admin
from app.services.approval_workflow_service import (
    decide_finance_approval,
    query_approval_tickets,
    submit_finance_approval,
)

bp = Blueprint("approvals", __name__, url_prefix="/api/admin/approvals")


@bp.route("", methods=["GET"])
@require_admin
def list_approvals():
    status = request.args.get("status")
    db_path = current_app.config.get("DB_PATH")
    with tx_context(db_path) as conn:
        return jsonify({"tickets": query_approval_tickets(conn, status=status)})


@bp.route("", methods=["POST"])
@require_admin
def create_approval():
    data = request.get_json(silent=True) or {}
    db_path = current_app.config.get("DB_PATH")
    try:
        with tx_context(db_path, immediate=True) as conn:
            res = submit_finance_approval(
                conn,
                ticket_type=str(data.get("ticket_type") or "MANUAL_ADJUSTMENT"),
                tenant_id=str(data["tenant_id"]),
                ref_object_id=str(data.get("ref_object_id") or ""),
                amount_cents=int(data["amount_cents"]),
                requested_by=str(data.get("requested_by") or "ops_maker"),
                reason=str(data.get("reason") or ""),
            )
        return jsonify(res), 201
    except (KeyError, TypeError, ValueError) as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/<ticket_id>/decide", methods=["POST"])
@require_admin
def decide_approval(ticket_id: str):
    data = request.get_json(silent=True) or {}
    approver = str(data.get("approver") or "finance_checker").strip()
    decision = str(data.get("decision") or "APPROVE").strip()
    db_path = current_app.config.get("DB_PATH")
    try:
        with tx_context(db_path) as conn:
            res = decide_finance_approval(conn, ticket_id, approver=approver, decision=decision)
        return jsonify(res)
    except LookupError as e:
        return jsonify({"error": str(e)}), 404
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
