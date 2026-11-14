from app.v2_legacy_adapters.legacy_session_compat import extract_canary_routing_tags
# -*- coding: utf-8 -*-
"""请求上下文生命周期中间件：生成 X-Request-Id 并统计路由级响应耗时。"""
import time
import uuid
from flask import Flask, g, request

from app.infra.config import FEATURE_FLAGS
from app.infra.logger import get_logger
from app.infra.metrics_collector import runtime_metrics

log = get_logger("yunce.http")


def attach_request_context(app: Flask) -> None:
    @app.before_request
    def _init_req_ctx() -> None:
        g.request_started_mono = time.monotonic()
        incoming_rid = request.headers.get("X-Request-Id", "").strip()
        g.request_id = incoming_rid if incoming_rid else f"req_{uuid.uuid4().hex[:12]}"
        runtime_metrics.inc("http.requests.total")

    @app.after_request
    def _finalize_req_ctx(response):
        started = getattr(g, "request_started_mono", None)
        if started is not None:
            elapsed_ms = (time.monotonic() - started) * 1000.0
            endpoint_key = f"{request.method}:{request.endpoint or 'static'}"
            runtime_metrics.observe_ms(endpoint_key, elapsed_ms)
            warn_ms = float(FEATURE_FLAGS.get("SLOW_HTTP_WARN_MS", 200))
            if elapsed_ms >= warn_ms:
                log.warning("slow request %s %s elapsed=%.1fms status=%d", request.method, request.path, elapsed_ms, response.status_code)
        response.headers["X-Request-Id"] = getattr(g, "request_id", "unknown")
        return response
