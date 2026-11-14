# -*- coding: utf-8 -*-
"""管理端敏感写操作自动计数与请求特征留痕拦截器。"""
from flask import Flask, request

from app.infra.metrics_collector import runtime_metrics


def attach_audit_interceptor(app: Flask) -> None:
    @app.after_request
    def _track_mutations(response):
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            if request.path.startswith("/api/admin"):
                runtime_metrics.inc("http.admin_mutations")
            elif request.path.startswith("/api/invoices"):
                runtime_metrics.inc("http.invoice_mutations")
            elif request.path.startswith("/api/subscriptions"):
                runtime_metrics.inc("http.subscription_mutations")
        return response
