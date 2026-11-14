# -*- coding: utf-8 -*-
"""租户 Token（含 v1 兼容头回退）与管理员密钥鉴权装饰器。"""
from functools import wraps
from flask import g, jsonify, request

from app.infra.config import ADMIN_API_KEY
from app.infra.db import get_connection, normalize_tenant_record
from app.middleware.legacy_header_shim import extract_effective_tenant_token


def require_tenant(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        token = getattr(g, "resolved_tenant_token", None) or extract_effective_tenant_token()
        if not token:
            return jsonify({"error": "缺少 X-Tenant-Token 鉴权头"}), 401
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM tenants WHERE api_token = ?", (token,)
            ).fetchone()
            if not row:
                return jsonify({"error": "无效的租户 Token"}), 401
            g.tenant = normalize_tenant_record(row)
        finally:
            conn.close()
        return fn(*args, **kwargs)

    return wrapper


def require_admin(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        key = request.headers.get("X-Admin-Key", "").strip()
        if key != ADMIN_API_KEY:
            return jsonify({"error": "管理员鉴权失败"}), 403
        return fn(*args, **kwargs)

    return wrapper
