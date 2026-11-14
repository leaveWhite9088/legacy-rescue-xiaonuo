# -*- coding: utf-8 -*-
"""HTTP 请求中间件栈：负责 TraceId 注入、老客户端请求头转换、慢请求监控与接口废弃提示。"""
from flask import Flask

from app.middleware.audit_interceptor import attach_audit_interceptor
from app.middleware.deprecation_guard import attach_deprecation_headers
from app.middleware.legacy_header_shim import attach_legacy_header_shim
from app.middleware.request_context import attach_request_context


def register_middlewares(app: Flask) -> None:
    attach_request_context(app)
    attach_legacy_header_shim(app)
    attach_audit_interceptor(app)
    attach_deprecation_headers(app)
