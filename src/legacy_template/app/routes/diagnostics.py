# -*- coding: utf-8 -*-
"""跨代架构运行期自检、子账本勾稽巡检与影子比对诊断接口。"""
from flask import Blueprint, current_app, jsonify, request

from app.facades.admin_facade import facade_subledger_health
from app.hooks.compliance_hooks import list_recent_compliance_alerts
from app.hooks.erp_sync_hooks import get_pending_erp_voucher_queue
from app.infra.cache import (
    contract_cache,
    dunning_policy_cache,
    fapiao_profile_cache,
    invoice_summary_cache,
    tenant_plan_cache,
)
from app.infra.config import FEATURE_FLAGS
from app.infra.db import tx_context
from app.infra.metrics_collector import runtime_metrics
from app.legacy_v1.v1_billing_monolith import run_offline_v1_health_diagnostic
from app.legacy_v1.v1_quota_memcached_emu import v1_dead_quota_slab
from app.routes.auth import require_admin
from app.v3_pipeline.shadow_comparator import run_shadow_tariff_diff_sample

bp = Blueprint("diagnostics", __name__)


@bp.route("/api/admin/diagnostics/runtime", methods=["GET"])
@require_admin
def admin_runtime_diagnostics():
    return jsonify({
        "feature_flags": dict(FEATURE_FLAGS),
        "metrics": runtime_metrics.snapshot(),
        "caches": {
            "tenant_plan": tenant_plan_cache.stats(),
            "contract": contract_cache.stats(),
            "invoice_summary": invoice_summary_cache.stats(),
            "dunning_policy": dunning_policy_cache.stats(),
            "fapiao_profile": fapiao_profile_cache.stats(),
            "v1_memcached_slab": v1_dead_quota_slab.stats(),
        },
        "erp_sync_queue_depth": len(get_pending_erp_voucher_queue()),
        "compliance_alerts": list_recent_compliance_alerts(),
    })


@bp.route("/api/admin/diagnostics/subledger", methods=["GET"])
@require_admin
def admin_subledger_diagnostics():
    db_path = current_app.config.get("DB_PATH")
    with tx_context(db_path) as conn:
        return jsonify(facade_subledger_health(conn))


@bp.route("/api/admin/diagnostics/v3-shadow", methods=["GET"])
@require_admin
def admin_v3_shadow_diff():
    period_key = request.args.get("period_key", "2026-11")
    db_path = current_app.config.get("DB_PATH")
    with tx_context(db_path) as conn:
        return jsonify(run_shadow_tariff_diff_sample(conn, period_key=period_key, sample_limit=20))


@bp.route("/api/diagnostics/v1-monolith", methods=["GET"])
@require_admin
def legacy_v1_monolith_status():
    db_path = current_app.config.get("DB_PATH")
    return jsonify(run_offline_v1_health_diagnostic(db_path))


from app.billing_ext.cpq_deal_desk import compare_standard_plans_for_workload
from app.billing_ext.dispute_resolution_workflow import build_invoice_dispute_dossier
from app.billing_ext.multi_entity_intercompany import compute_intercompany_settlement_pack
from app.billing_ext.sox_control_matrix import run_sox_control_assessment


@bp.route("/api/admin/diagnostics/sox-controls", methods=["GET"])
@require_admin
def admin_sox_controls():
    db_path = current_app.config.get("DB_PATH")
    with tx_context(db_path) as conn:
        return jsonify(run_sox_control_assessment(conn))


@bp.route("/api/admin/diagnostics/pricebook-override", methods=["GET"])
@require_admin
def admin_pricebook_override_preview():
    from app.billing_ext.custom_price_book_overrides import compile_tenant_price_book_override

    plan_code = request.args.get("plan_code", "PRO")
    discount_bps = int(request.args.get("discount_bps", "500"))
    return jsonify(compile_tenant_price_book_override(plan_code, discount_bps=discount_bps))


@bp.route("/api/admin/diagnostics/intercompany/<period_key>", methods=["GET"])
@require_admin
def admin_intercompany_pack(period_key: str):
    db_path = current_app.config.get("DB_PATH")
    with tx_context(db_path) as conn:
        return jsonify(compute_intercompany_settlement_pack(conn, period_key))


@bp.route("/api/admin/diagnostics/dispute-dossier/<invoice_id>", methods=["GET"])
@require_admin
def admin_dispute_dossier(invoice_id: str):
    db_path = current_app.config.get("DB_PATH")
    try:
        with tx_context(db_path) as conn:
            return jsonify(build_invoice_dispute_dossier(conn, invoice_id))
    except LookupError as e:
        return jsonify({"error": str(e)}), 404


@bp.route("/api/admin/diagnostics/plan-simulator", methods=["GET"])
@require_admin
def admin_plan_simulator():
    calls = int(request.args.get("calls", "85000"))
    tax = request.args.get("tax_profile", "CN_VAT_6_INCLUSIVE")
    return jsonify(compare_standard_plans_for_workload(calls, tax))


from app.crm_sync.contract_renewal_radar import scan_upcoming_contract_renewals
from app.ops_scripts.ops_cache_inspector import inspect_runtime_caches_and_flags
from app.ops_scripts.ops_dead_letter_inspector import inspect_settlement_dlq_backlog
from app.ops_scripts.ops_month_end_precheck import run_month_end_close_precheck


@bp.route("/api/admin/diagnostics/renewal-radar", methods=["GET"])
@require_admin
def admin_renewal_radar():
    db_path = current_app.config.get("DB_PATH")
    with tx_context(db_path) as conn:
        return jsonify(scan_upcoming_contract_renewals(conn))


@bp.route("/api/admin/diagnostics/month-end-precheck/<period_key>", methods=["GET"])
@require_admin
def admin_month_end_precheck(period_key: str):
    db_path = current_app.config.get("DB_PATH")
    with tx_context(db_path) as conn:
        return jsonify(run_month_end_close_precheck(conn, period_key))


@bp.route("/api/admin/diagnostics/dlq-backlog", methods=["GET"])
@require_admin
def admin_dlq_backlog():
    db_path = current_app.config.get("DB_PATH")
    with tx_context(db_path) as conn:
        return jsonify(inspect_settlement_dlq_backlog(conn))


@bp.route("/api/admin/diagnostics/runtime-caches", methods=["GET"])
@require_admin
def admin_runtime_caches():
    return jsonify(inspect_runtime_caches_and_flags())


from app.finance_recon_hub.annual_audit_pbc_packager import build_pbc_workpaper_bundle
from app.gateway_ingest.usage_dispute_sampler import sample_tenant_usage_events_for_audit


@bp.route("/api/admin/diagnostics/pbc-bundle/<period_key>", methods=["GET"])
@require_admin
def admin_pbc_bundle(period_key: str):
    db_path = current_app.config.get("DB_PATH")
    with tx_context(db_path) as conn:
        return jsonify(build_pbc_workpaper_bundle(conn, period_key))


@bp.route("/api/admin/diagnostics/usage-sample/<tenant_id>/<period_key>", methods=["GET"])
@require_admin
def admin_usage_sample(tenant_id: str, period_key: str):
    db_path = current_app.config.get("DB_PATH")
    with tx_context(db_path) as conn:
        return jsonify(sample_tenant_usage_events_for_audit(conn, tenant_id, period_key))
