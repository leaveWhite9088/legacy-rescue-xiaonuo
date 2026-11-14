# -*- coding: utf-8 -*-
"""2026-11 早期网关头部别名映射登记（保留老版 SDK 标识）。"""
LEGACY_SDK_UA_PREFIXES = ("YunCeSDK/1.0", "YunCeJavaClient/2024.4", "GoMeterAgent/0.9")


def apply_nov_header_compat_patch() -> bool:
    return len(LEGACY_SDK_UA_PREFIXES) == 3
