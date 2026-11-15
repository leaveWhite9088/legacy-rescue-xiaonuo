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
    run_standalone_period_audit_snapshot,
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


@bp.route("/adjustments/<adjustment_id>/apply", methods=["POST"])
@require_admin
def admin_apply_adjustment(adjustment_id: str):
    from app.domain.reconcile import apply_adjustment_to_open_invoice

    data = request.get_json(silent=True) or {}
    target_invoice_id = str(data.get("target_invoice_id") or "").strip()
    approval_ticket_id = str(data.get("approval_ticket_id") or "").strip() or None
    if not target_invoice_id:
        return jsonify({"error": "缺少 target_invoice_id"}), 400
    db_path = current_app.config.get("DB_PATH")
    try:
        with tx_context(db_path, immediate=True) as conn:
            res = apply_adjustment_to_open_invoice(
                conn,
                adjustment_id,
                target_invoice_id,
                actor="admin_api",
                approval_ticket_id=approval_ticket_id,
            )
        return jsonify(res)
    except LookupError as e:
        return jsonify({"error": str(e)}), 404
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


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


@bp.route("/disputes/<dispute_id>/resolve", methods=["POST"])
@require_admin
def admin_resolve_dispute(dispute_id: str):
    from app.services.billing_service import resolve_invoice_dispute_admin

    data = request.get_json(silent=True) or {}
    db_path = current_app.config.get("DB_PATH")
    try:
        with tx_context(db_path, immediate=True) as conn:
            res = resolve_invoice_dispute_admin(conn, dispute_id, str(data.get("decision") or ""), actor="admin_api")
        return jsonify(res)
    except LookupError as e:
        return jsonify({"error": str(e)}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/bank-statements/import", methods=["POST"])
@require_admin
def admin_import_bank_csv():
    from app.services.bank_statement_matcher import import_and_match_bank_csv

    data = request.get_json(silent=True) or {}
    csv_text = str(data.get("csv_text") or "")
    db_path = current_app.config.get("DB_PATH")
    with tx_context(db_path, immediate=True) as conn:
        return jsonify(import_and_match_bank_csv(conn, csv_text))


@bp.route("/bank-statements/<import_id>/claim", methods=["POST"])
@require_admin
def admin_claim_bank_statement(import_id: str):
    from app.services.bank_statement_matcher import manual_claim_bank_statement

    data = request.get_json(silent=True) or {}
    tenant_id = str(data.get("tenant_id") or "").strip()
    db_path = current_app.config.get("DB_PATH")
    try:
        with tx_context(db_path, immediate=True) as conn:
            return jsonify(manual_claim_bank_statement(conn, import_id, tenant_id, operator="admin_api"))
    except LookupError as e:
        return jsonify({"error": str(e)}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/treasury/fx-reval/<period_key>", methods=["POST"])
@require_admin
def admin_reval_fx_ledger(period_key: str):
    from app.treasury.fx_hedging_revaluation import revalue_period_fx_ledger

    data = request.get_json(silent=True) or {}
    rates = {str(k).upper(): int(v) for k, v in (data.get("closing_rates_bps") or {}).items()}
    db_path = current_app.config.get("DB_PATH")
    with tx_context(db_path) as conn:
        return jsonify(revalue_period_fx_ledger(conn, period_key, rates))


@bp.route("/treasury/wht-calc", methods=["POST"])
@require_admin
def admin_calc_crossborder_wht():
    from app.billing_ext.tax_withholding_crossborder import calculate_crossborder_wht_settlement

    data = request.get_json(silent=True) or {}
    return jsonify(
        calculate_crossborder_wht_settlement(
            invoice_net_cents=int(data.get("invoice_net_cents", 0)),
            jurisdiction_code=str(data.get("jurisdiction_code") or "SG"),
            has_tax_residency_cert=bool(data.get("has_tax_residency_cert", True)),
            contract_gross_up_clause=bool(data.get("contract_gross_up_clause", False)),
            is_royalty_license=bool(data.get("is_royalty_license", False)),
        )
    )


@bp.route("/treasury/channel-fees/<period_key>", methods=["GET"])
@require_admin
def admin_audit_channel_fees(period_key: str):
    from app.treasury.clearinghouse_fee_auditor import audit_period_payment_channel_fees

    ch = request.args.get("channel_code", "WECHAT_NATIVE_V2")
    db_path = current_app.config.get("DB_PATH")
    with tx_context(db_path) as conn:
        return jsonify(audit_period_payment_channel_fees(conn, period_key, channel_code=ch))


@bp.route("/escrow/apply-to-invoice", methods=["POST"])
@require_admin
def admin_apply_escrow():
    from app.treasury.escrow_deposit_manager import apply_escrow_to_invoice

    data = request.get_json(silent=True) or {}
    tenant_id = str(data.get("tenant_id") or "").strip()
    invoice_id = str(data.get("invoice_id") or "").strip()
    try:
        amount_cents = int(data.get("amount_cents", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "amount_cents 必须为整数"}), 400
    db_path = current_app.config.get("DB_PATH")
    try:
        with tx_context(db_path, immediate=True) as conn:
            return jsonify(apply_escrow_to_invoice(conn, tenant_id, invoice_id, amount_cents, operator="admin_api"))
    except LookupError as e:
        return jsonify({"error": str(e)}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


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


@bp.route("/reports/invoices-page.csv", methods=["GET"])
@require_admin
def download_paginated_invoices_csv():
    from app.services.report_export_service import export_paginated_invoices_csv

    period_key = request.args.get("period_key", "2026-11")
    page = int(request.args.get("page", "1"))
    page_size = int(request.args.get("page_size", "20"))
    db_path = current_app.config.get("DB_PATH")
    with tx_context(db_path) as conn:
        csv_str = export_paginated_invoices_csv(conn, period_key, page=page, page_size=page_size)
    return Response(csv_str, mimetype="text/csv; charset=utf-8")


@bp.route("/webhooks/dispatch", methods=["POST"])
@require_admin
def admin_dispatch_webhooks():
    from app.services.webhook_dispatcher import dispatch_queued_webhooks

    db_path = current_app.config.get("DB_PATH")
    with tx_context(db_path, immediate=True) as conn:
        return jsonify(dispatch_queued_webhooks(conn))


@bp.route("/webhooks/verify", methods=["POST"])
@require_admin
def admin_verify_webhook_sig():
    from app.infra.security import verify_webhook_signature

    data = request.get_json(silent=True) or {}
    ok = verify_webhook_signature(
        timestamp_str=str(data.get("timestamp") or ""),
        body_json=str(data.get("body") or ""),
        signature_header=str(data.get("signature") or ""),
        now_epoch=float(data["now_epoch"]) if "now_epoch" in data and data["now_epoch"] is not None else None,
    )
    return jsonify({"valid": bool(ok)})


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


@bp.route("/reports/standalone-audit/<period_key>", methods=["GET"])
@require_admin
def admin_standalone_audit(period_key: str):
    db_path = current_app.config.get("DB_PATH")
    try:
        return jsonify(run_standalone_period_audit_snapshot(db_path, period_key))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


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
    try:
        target = resolve_export_filepath(export_root, filename)
        with open(target, "r", encoding="utf-8") as f:
            return Response(f.read(), mimetype="text/plain; charset=utf-8")
    except (ValueError, PermissionError) as e:
        return jsonify({"error": str(e)}), 400
    except FileNotFoundError:
        return jsonify({"error": "导出文件不存在"}), 404
