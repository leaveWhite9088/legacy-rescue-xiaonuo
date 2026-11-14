# -*- coding: utf-8 -*-
"""2023-2024 第一代计费单体遗留模块包 (v1 Monolith)。
警告：部分存量老合同算价与历史元字符串解析仍由 v2 兼容桥接层直接调用，请勿整包删除。
"""
from app.legacy_v1.v1_currency_shim import (
    format_v1_yuan_display,
    parse_v1_yuan_string,
)
from app.legacy_v1.v1_flat_tariff import (
    compute_v1_legacy_contract_bill,
    resolve_v1_override_payload,
)

__all__ = [
    "compute_v1_legacy_contract_bill",
    "resolve_v1_override_payload",
    "parse_v1_yuan_string",
    "format_v1_yuan_display",
]
