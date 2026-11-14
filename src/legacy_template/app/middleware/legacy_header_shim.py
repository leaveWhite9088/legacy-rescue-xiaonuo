# -*- coding: utf-8 -*-
"""2024 老版本 SDK 请求头兼容转换中间件：
早期制造业私有化网关使用 X-Legacy-Api-Token 或 Authorization: TenantToken <tok> 传参。
"""
from flask import Flask, g, request


def extract_effective_tenant_token() -> str:
    direct = request.headers.get("X-Tenant-Token", "").strip()
    if direct:
        return direct
    legacy_hdr = request.headers.get("X-Legacy-Api-Token", "").strip()
    if legacy_hdr:
        return legacy_hdr
    auth = request.headers.get("Authorization", "").strip()
    if auth.lower().startswith("tenanttoken "):
        return auth[12:].strip()
    return ""


def attach_legacy_header_shim(app: Flask) -> None:
    @app.before_request
    def _detect_client_generation() -> None:
        v1_build = request.headers.get("X-V1-Client-Build", "").strip()
        g.client_sdk_generation = "v1_2024" if v1_build else "v2_2025"
        g.resolved_tenant_token = extract_effective_tenant_token()
