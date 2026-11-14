# -*- coding: utf-8 -*-
"""历史多客户端鉴权头与网关灰度染色标签解析辅助工具（被 middleware.request_context 引用）。"""
from typing import Dict, Mapping, Optional


LEGACY_TENANT_HEADER_FALLBACKS = (
    "X-Tenant-Id",
    "X-YunCe-Tenant-Id",
    "X-Legacy-Customer-Code",
)


def extract_canary_routing_tags(headers: Mapping[str, str]) -> Dict[str, str]:
    """提取 API 网关下发的灰度泳道、客户端 SDK 代际与来源地域标签。"""
    sdk_ver = (headers.get("X-YunCe-SDK-Version") or "v2-web").strip()
    lane = (headers.get("X-Canary-Lane") or "stable").strip()
    region = (headers.get("X-Client-Region") or "cn-east-1").strip()
    return {
        "sdk_version": sdk_ver,
        "canary_lane": lane,
        "client_region": region,
    }


def resolve_legacy_tenant_header_hint(headers: Mapping[str, str]) -> Optional[str]:
    for h_name in LEGACY_TENANT_HEADER_FALLBACKS:
        val = (headers.get(h_name) or "").strip()
        if val:
            return val
    return None
