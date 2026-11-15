# -*- coding: utf-8 -*-
"""计量事件上报与配额使用汇总查询路由（经由 metering_facade 编排）。"""
from datetime import datetime, timezone
from flask import Blueprint, current_app, g, jsonify, request

from app.facades.metering_facade import facade_get_usage_summary, facade_ingest_usage
from app.gateway_ingest.batch_ingest_service import ingest_gateway_usage_batch
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


@bp.route("/batch", methods=["POST"])
@require_tenant
def ingest_usage_batch_route():
    data = request.get_json(silent=True) or {}
    events = data.get("events")
    db_path = current_app.config.get("DB_PATH")
    try:
        with tx_context(db_path, immediate=True) as conn:
            res = ingest_gateway_usage_batch(conn, tenant_id=g.tenant["id"], events=events)
        return jsonify(res), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/summary", methods=["GET"])
@require_tenant
def get_usage_summary():
    period_key = request.args.get("period_key") or datetime.now(timezone.utc).strftime("%Y-%m")
    db_path = current_app.config.get("DB_PATH")
    with tx_context(db_path) as conn:
        snap = facade_get_usage_summary(conn, g.tenant["id"], period_key)
    return jsonify(snap)


@bp.route("/merge-shards", methods=["POST"])
@require_tenant
def merge_usage_shards_route():
    from app.gateway_ingest.cross_region_shard_merger import merge_regional_usage_shards

    data = request.get_json(silent=True) or {}
    shards = data.get("shards")
    db_path = current_app.config.get("DB_PATH")
    try:
        with tx_context(db_path, immediate=True) as conn:
            res = merge_regional_usage_shards(conn, tenant_id=g.tenant["id"], shard_records=shards)
        return jsonify(res), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/custom-tier-quote", methods=["POST"])
@require_tenant
def quote_custom_tier_overage():
    from app.domain.pricing import compute_custom_tier_overage_cents

    data = request.get_json(silent=True) or {}
    total_usage = int(data.get("total_usage", 0))
    included_quota = int(data.get("included_quota", 10000))
    raw_bands = data.get("cumulative_bands") or [[10000, 3], [50000, 2], [None, 1]]
    bands = [(None if b[0] is None else int(b[0]), int(b[1])) for b in raw_bands]
    cents = compute_custom_tier_overage_cents(total_usage, included_quota, bands)
    return jsonify({"overage_fee_cents": cents})
