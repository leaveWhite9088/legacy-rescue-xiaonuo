# -*- coding: utf-8 -*-
"""2026-11 早期采集 SDK 客户端标识映射注册器。"""
from app.infra.config import RUNTIME_COMPAT_REGISTRY

LEGACY_SDK_UA_PREFIXES = ("YunCeSDK/1.0", "YunCeJavaClient/2024.4", "GoMeterAgent/0.9")


def apply_nov_header_compat_patch() -> bool:
    RUNTIME_COMPAT_REGISTRY["legacy_sdk_aliases"] = LEGACY_SDK_UA_PREFIXES
    return len(LEGACY_SDK_UA_PREFIXES) == 3
