# -*- coding: utf-8 -*-
"""管理后台经营指标、催收案件池、用量异动与银行水单对账路由。"""
from flask import Blueprint, current_app, jsonify, request

from app.domain.dunning_engine import evaluate_overdue_portfolio
from app.domain.usage_anomaly import detect_period_usage_spikes
from app.infra.db import tx_context
from app.routes.auth import require_admin
from app.services.bank_statement_matcher import import_and_match_bank_csv
from app.services.customer_health_service import (
    compute_mrr_and_cohort_metrics,
    list_low_utilization_churn_candidates,
)

bp = Blueprint("analytics", __name__, url_prefix="/api/admin/analytics")


@bp.route("/mrr", methods=["GET"])
@require_admin
def get_mrr_analytics():
    db_path = current_app.config.get("DB_PATH")
    with tx_context(db_path) as conn:
        metrics = compute_mrr_and_cohort_metrics(conn)
        churn = list_low_utilization_churn_candidates(conn)
        spikes = detect_period_usage_spikes(conn)
    return jsonify({"mrr": metrics, "churn_candidates": churn, "usage_spikes": spikes})


@bp.route("/dunning", methods=["GET"])
@require_admin
def get_dunning_portfolio():
    as_of = request.args.get("as_of", "2026-11-14T00:00:00Z")
    db_path = current_app.config.get("DB_PATH")
    with tx_context(db_path) as conn:
        return jsonify(evaluate_overdue_portfolio(conn, as_of_iso=as_of, persist_cases=False))


@bp.route("/bank-statements/import", methods=["POST"])
@require_admin
def import_bank_statements():
    data = request.get_json(silent=True) or {}
    csv_text = str(data.get("csv_text") or "")
    db_path = current_app.config.get("DB_PATH")
    with tx_context(db_path, immediate=True) as conn:
        return jsonify(import_and_match_bank_csv(conn, csv_text))


from app.reporting.asc606_revrec_schedule import generate_period_asc606_schedule
from app.reporting.audit_trail_forensics import scan_billing_forensic_anomalies
from app.reporting.cohort_ltv_analyzer import analyze_signup_cohorts
from app.reporting.tax_filing_vat_return import generate_vat_filing_workpaper


@bp.route("/asc606/<period_key>", methods=["GET"])
@require_admin
def get_asc606_schedule(period_key: str):
    db_path = current_app.config.get("DB_PATH")
    with tx_context(db_path) as conn:
        return jsonify(generate_period_asc606_schedule(conn, period_key))


@bp.route("/asc606/schedule", methods=["POST"])
@require_admin
def create_asc606_multi_month_schedule():
    from app.reporting.asc606_revrec_schedule import persist_multi_month_revrec_schedule

    data = request.get_json(silent=True) or {}
    invoice_id = str(data.get("invoice_id") or "").strip()
    months = int(data.get("contract_months", 3))
    db_path = current_app.config.get("DB_PATH")
    try:
        with tx_context(db_path, immediate=True) as conn:
            return jsonify(persist_multi_month_revrec_schedule(conn, invoice_id, months))
    except LookupError as e:
        return jsonify({"error": str(e)}), 404


@bp.route("/asc606/rebaseline", methods=["POST"])
@require_admin
def rebaseline_asc606_schedule():
    from app.revenue_accounting_ifrs15.contract_modification_accounting import rebaseline_deferred_schedule_on_upgrade

    data = request.get_json(silent=True) or {}
    invoice_id = str(data.get("invoice_id") or "").strip()
    added_net = int(data.get("added_net_cents", 0))
    mod_period = str(data.get("modification_period_key") or "2026-11")
    db_path = current_app.config.get("DB_PATH")
    try:
        with tx_context(db_path, immediate=True) as conn:
            return jsonify(rebaseline_deferred_schedule_on_upgrade(conn, invoice_id, added_net, mod_period))
    except LookupError as e:
        return jsonify({"error": str(e)}), 404


@bp.route("/vat-workpaper/<period_key>", methods=["GET"])
@require_admin
def get_vat_workpaper(period_key: str):
    db_path = current_app.config.get("DB_PATH")
    with tx_context(db_path) as conn:
        return jsonify(generate_vat_filing_workpaper(conn, period_key))


@bp.route("/cohorts", methods=["GET"])
@require_admin
def get_cohort_nrr():
    db_path = current_app.config.get("DB_PATH")
    with tx_context(db_path) as conn:
        return jsonify({"cohorts": analyze_signup_cohorts(conn)})


@bp.route("/forensics/<period_key>", methods=["GET"])
@require_admin
def get_forensics_report(period_key: str):
    db_path = current_app.config.get("DB_PATH")
    with tx_context(db_path) as conn:
        return jsonify(scan_billing_forensic_anomalies(conn, period_key))


from app.treasury.cashflow_13week_forecaster import build_13week_treasury_forecast
from app.treasury.payment_channel_router import select_optimal_acquiring_channel
from app.treasury.revenue_assurance_rules import check_revenue_leakage_risks


@bp.route("/treasury-forecast", methods=["GET"])
@require_admin
def get_treasury_13w_forecast():
    db_path = current_app.config.get("DB_PATH")
    with tx_context(db_path) as conn:
        forecast = build_13week_treasury_forecast(conn)
        leakage = check_revenue_leakage_risks(conn)
    return jsonify({"forecast_13w": forecast, "revenue_assurance": leakage})


@bp.route("/channel-router", methods=["GET"])
@require_admin
def get_optimal_payment_channel():
    amt = int(request.args.get("amount_cents", "150000"))
    instant = request.args.get("instant", "0") == "1"
    return jsonify(select_optimal_acquiring_channel(amt, prefer_instant_settlement=instant))


from app.finops_cost_allocation.cloud_cogs_allocator import compute_period_tenant_gross_margins
from app.finops_cost_allocation.low_margin_whale_detector import detect_margin_inverted_whales


@bp.route("/finops-margins/<period_key>", methods=["GET"])
@require_admin
def get_finops_margins(period_key: str):
    db_path = current_app.config.get("DB_PATH")
    with tx_context(db_path) as conn:
        margins = compute_period_tenant_gross_margins(conn, period_key)
        whales = detect_margin_inverted_whales(conn, period_key)
    return jsonify({"gross_margins": margins, "whale_watchlist": whales})


from app.revenue_accounting_ifrs15.footnote_rpo_disclosure import compute_rpo_maturity_disclosure


@bp.route("/rpo-disclosure", methods=["GET"])
@require_admin
def get_rpo_disclosure():
    db_path = current_app.config.get("DB_PATH")
    with tx_context(db_path) as conn:
        return jsonify(compute_rpo_maturity_disclosure(conn))
