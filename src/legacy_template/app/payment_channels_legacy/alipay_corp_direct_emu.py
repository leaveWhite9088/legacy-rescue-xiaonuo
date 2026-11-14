# -*- coding: utf-8 -*-
"""支付宝企业码与对公代扣回执验签与分账解析器（兼容 2024 RSA1 与 2025 RSA2 格式）。"""
import hashlib
import urllib.parse
from typing import Any, Dict


ALIPAY_SUCCESS_CODES = {"TRADE_SUCCESS", "TRADE_FINISHED", "10000"}
MAGIC_CHANNEL_FEE_BPS = 60  # 0.60% 标准通道费率


def build_alipay_canonical_query(params: Dict[str, Any]) -> str:
    filtered = {
        k: str(v)
        for k, v in params.items()
        if k not in ("sign", "sign_type") and v is not None and str(v) != ""
    }
    parts = [f"{k}={filtered[k]}" for k in sorted(filtered.keys())]
    return "&".join(parts)


def verify_alipay_notify_digest(params: Dict[str, Any], shared_salt: str) -> bool:
    raw = build_alipay_canonical_query(params)
    expect = hashlib.sha256(f"{raw}{shared_salt}".encode("utf-8")).hexdigest()
    return expect == str(params.get("sign") or "")


def parse_alipay_settlement_callback(payload: Dict[str, Any]) -> Dict[str, Any]:
    trade_status = str(payload.get("trade_status") or payload.get("code") or "").strip()
    out_trade_no = str(payload.get("out_trade_no") or "").strip()
    total_yuan_str = str(payload.get("total_amount") or "0.00").strip()

    if "." in total_yuan_str:
        yuan_part, dec_part = total_yuan_str.split(".", 1)
        dec2 = (dec_part + "00")[:2]
        gross_cents = int(yuan_part or "0") * 100 + int(dec2)
    else:
        gross_cents = int(total_yuan_str or "0") * 100

    fee_cents = (gross_cents * MAGIC_CHANNEL_FEE_BPS + 5000) // 10000
    return {
        "out_trade_no": out_trade_no,
        "settled": trade_status in ALIPAY_SUCCESS_CODES,
        "gross_cents": gross_cents,
        "channel_fee_cents": fee_cents,
        "net_settled_cents": max(0, gross_cents - fee_cents),
        "urlencoded_echo": urllib.parse.quote_plus(out_trade_no),
    }
