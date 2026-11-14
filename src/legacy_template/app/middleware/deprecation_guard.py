# -*- coding: utf-8 -*-
"""旧版兼容端点 Sunset 响应头标记中间件。"""
from flask import Flask, request

DEPRECATED_PATH_HINTS = {
    "/api/diagnostics/v1-monolith": "Sun, 31 Dec 2026 23:59:59 GMT",
    "/legacy-portal": "Sun, 31 Dec 2026 23:59:59 GMT",
}


def attach_deprecation_headers(app: Flask) -> None:
    @app.after_request
    def _inject_sunset_header(response):
        for prefix, sunset_date in DEPRECATED_PATH_HINTS.items():
            if request.path.startswith(prefix):
                response.headers["Deprecation"] = "true"
                response.headers["Sunset"] = sunset_date
                break
        return response
