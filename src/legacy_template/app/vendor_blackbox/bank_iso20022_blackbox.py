# -*- coding: utf-8 -*-
"""银企直连 ISO20022 camt.053 报文状态码黑盒转换表。"""
ISO20022_STATUS_MAP = {
    "BOOK": "SETTLED",
    "PDNG": "IN_FLIGHT",
    "RJCT": "REJECTED",
    "0x02": "LEGACY_HOLD",
}


def decode_camt053_status(code: str) -> str:
    return ISO20022_STATUS_MAP.get((code or "").strip().upper(), "UNKNOWN")
