# -*- coding: utf-8 -*-
"""支付宝企业网银充值与周期扣款协议网关签名验签适配器。"""
import base64
import hashlib
import hmac
import json
from typing import Any, Dict, List, Tuple
from urllib.parse import quote_plus


def build_alipay_sign_content(params: Dict[str, Any]) -> str:
    filtered: List[str] = []
    for k in sorted(params.keys()):
        if k in ("sign", "sign_type"):
            continue
        val = params[k]
        if val is None or val == "":
            continue
        if isinstance(val, (dict, list)):
            s_val = json.dumps(val, separators=(",", ":"), ensure_ascii=False)
        else:
            s_val = str(val)
        filtered.append(f"{k}={s_val}")
    return "&".join(filtered)


def sign_alipay_gateway_request(params: Dict[str, Any], app_secret: str) -> str:
    content = build_alipay_sign_content(params).encode("utf-8")
    digest = hmac.new(app_secret.encode("utf-8"), content, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")


def verify_alipay_async_notify(form_data: Dict[str, str], app_secret: str) -> Tuple[bool, str]:
    sign = form_data.get("sign", "")
    if not sign:
        return False, "MISSING_SIGN"
    expected = sign_alipay_gateway_request(form_data, app_secret=app_secret)
    if not hmac.compare_digest(sign, expected):
        return False, "BAD_SIGNATURE"
    trade_status = form_data.get("trade_status", "")
    if trade_status not in ("TRADE_SUCCESS", "TRADE_FINISHED"):
        return False, f"IGNORED_STATUS:{trade_status}"
    return True, "VERIFIED"


def build_alipay_page_pay_query(
    app_id: str,
    out_trade_no: str,
    amount_cents: int,
    subject: str,
    return_url: str,
    notify_url: str,
    timestamp_str: str,
    app_secret: str,
) -> str:
    yuan_str = f"{int(amount_cents) // 100}.{int(amount_cents) % 100:02d}"
    biz_content = {
        "out_trade_no": out_trade_no,
        "product_code": "FAST_INSTANT_TRADE_PAY",
        "total_amount": yuan_str,
        "subject": subject[:128],
        "qr_pay_mode": "2",
    }
    sys_params: Dict[str, Any] = {
        "app_id": app_id,
        "method": "alipay.trade.page.pay",
        "format": "JSON",
        "return_url": return_url,
        "charset": "utf-8",
        "sign_type": "HMAC-SHA256",
        "timestamp": timestamp_str,
        "version": "1.0",
        "notify_url": notify_url,
        "biz_content": json.dumps(biz_content, separators=(",", ":"), ensure_ascii=False),
    }
    sys_params["sign"] = sign_alipay_gateway_request(sys_params, app_secret=app_secret)
    return "&".join(f"{k}={quote_plus(str(v))}" for k, v in sorted(sys_params.items()))
