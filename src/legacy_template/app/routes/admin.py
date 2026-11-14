# -*- coding: utf-8 -*-
"""财务与运营管理后台接口：租户、账期、调账、总账凭证、批处理与对账导出。"""
import json
from flask import Blueprint, Response, current_app, jsonify, request

from app.facades.admin_facade import (
    facade_admin_overview,
    facade_admin_periods,
    facade_audit_logs,
    facade_close_period,
    facade_gl_journal,
    facade_list_adjustments,
    facade_reconcile_period,
)
from app.infra.config import EXPORT_DIR
from app.infra.db import tx_context
from app.infra.security import resolve_export_filepath
from app.jobs.scheduler import run_all_jobs
from app.routes.auth import require_admin
from app.services.report_export_service import (
    export_ar_aging_csv,
    export_kingdee_voucher_xml,
    export_tenant_legacy_statement_txt,
)

bp = Blueprint("admin", __name__, url_prefix="/api/admin")


@bp.route("/tenants", methods=["GET"])
@require_admin
def list_tenants():
    limit = min(500, int(request.args.get("limit", "200")))
    db_path = current_app.config.get("DB_PATH")
    with tx_context(db_path) as conn:
        return jsonify(facade_admin_overview(conn, limit=limit))


@bp.route("/periods", methods=["GET"])
@require_admin
def list_periods():
    db_path = current_app.config.get("DB_PATH")
    with tx_context(db_path) as conn:
        return jsonify(facade_admin_periods(conn))


@bp.route("/periods/<period_key>/close", methods=["POST"])
@require_admin
def close_period(period_key: str):
    db_path = current_app.config.get("DB_PATH")
    try:
        with tx_context(db_path, immediate=True) as conn:
            res = facade_close_period(conn, period_key, actor="admin_api")
        return jsonify(res)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/reconcile/<period_key>", methods=["GET"])
@require_admin
def get_reconciliation(period_key: str):
    db_path = current_app.config.get("DB_PATH")
    with tx_context(db_path) as conn:
        return jsonify(facade_reconcile_period(conn, period_key))


@bp.route("/adjustments", methods=["GET"])
@require_admin
def list_adjustments():
    db_path = current_app.config.get("DB_PATH")
    with tx_context(db_path) as conn:
        return jsonify(facade_list_adjustments(conn))


@bp.route("/gl/<period_key>", methods=["GET"])
@require_admin
def get_gl_journal(period_key: str):
    db_path = current_app.config.get("DB_PATH")
    with tx_context(db_path, immediate=True) as conn:
        return jsonify(facade_gl_journal(conn, period_key))


@bp.route("/audit-logs", methods=["GET"])
@require_admin
def get_audit_logs():
    db_path = current_app.config.get("DB_PATH")
    with tx_context(db_path) as conn:
        return jsonify(facade_audit_logs(conn, limit=100))


@bp.route("/reports/kingdee-xml/<period_key>", methods=["GET"])
@require_admin
def download_kingdee_xml(period_key: str):
    db_path = current_app.config.get("DB_PATH")
    with tx_context(db_path) as conn:
        xml_str = export_kingdee_voucher_xml(conn, period_key)
    return Response(xml_str, mimetype="application/xml; charset=utf-8")


@bp.route("/reports/ar-aging.csv", methods=["GET"])
@require_admin
def download_ar_aging_csv():
    db_path = current_app.config.get("DB_PATH")
    with tx_context(db_path) as conn:
        csv_str = export_ar_aging_csv(conn)
    return Response(csv_str, mimetype="text/csv; charset=utf-8")


@bp.route("/reports/legacy-statement/<tenant_id>/<period_key>", methods=["GET"])
@require_admin
def download_legacy_statement(tenant_id: str, period_key: str):
    db_path = current_app.config.get("DB_PATH")
    try:
        with tx_context(db_path) as conn:
            txt = export_tenant_legacy_statement_txt(conn, tenant_id, period_key)
        return Response(txt, mimetype="text/plain; charset=utf-8")
    except LookupError as e:
        return jsonify({"error": str(e)}), 404


# 后台批处理与对账导出接口
@bp.route("/jobs/run", methods=["POST"])
def trigger_jobs():
    data = request.get_json(silent=True) or {}
    as_of = data.get("as_of")
    db_path = current_app.config.get("DB_PATH")
    res = run_all_jobs(db_path=db_path, as_of_iso=as_of)
    return jsonify(res)


@bp.route("/reconcile/export", methods=["GET"])
def export_reconcile_file():
    filename = request.args.get("file", "")
    if not filename:
        period_key = request.args.get("period_key", "2026-11")
        db_path = current_app.config.get("DB_PATH")
        with tx_context(db_path) as conn:
            rep = facade_reconcile_period(conn, period_key)
        return Response(
            json.dumps(rep, ensure_ascii=False, indent=2),
            mimetype="application/json",
        )
    export_root = current_app.config.get("EXPORT_DIR", EXPORT_DIR)
    target = resolve_export_filepath(export_root, filename)
    with open(target, "r", encoding="utf-8") as f:
        return Response(f.read(), mimetype="text/plain; charset=utf-8")
