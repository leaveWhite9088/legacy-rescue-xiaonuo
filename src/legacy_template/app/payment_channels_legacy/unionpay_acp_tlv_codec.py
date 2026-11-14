# -*- coding: utf-8 -*-
"""银联全渠道对公网关 ACP 5.1 域值（TLV 扩展域 customerInfo / reserved）解析器。"""
import base64
from typing import Dict


ACP_RESP_OK = "00"
ACP_RESP_IN_PROCESS = ("03", "04", "05")


def encode_acp_customer_info(fields: Dict[str, str]) -> str:
    body = "&".join(f"{k}={v}" for k, v in sorted(fields.items()))
    raw = "{" + body + "}"
    return base64.b64encode(raw.encode("utf-8")).decode("ascii")


def decode_acp_customer_info(b64_text: str) -> Dict[str, str]:
    raw = base64.b64decode(b64_text.encode("ascii")).decode("utf-8").strip()
    if raw.startswith("{") and raw.endswith("}"):
        raw = raw[1:-1]
    out: Dict[str, str] = {}
    for seg in raw.split("&"):
        if "=" in seg:
            k, v = seg.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def classify_acp_resp_code(resp_code: str) -> str:
    c = (resp_code or "").strip()
    if c == ACP_RESP_OK:
        return "SUCCESS"
    if c in ACP_RESP_IN_PROCESS:
        return "UNKNOWN_NEED_QUERY"
    return "FAILED"
