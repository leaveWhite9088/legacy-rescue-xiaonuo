# -*- coding: utf-8 -*-
"""微信支付商户平台 v2 XML 遗留协议签名、异步回调验签与资金账单对账单解析器。
说明：2024 年接入的企业扫码充值通道仍沿用 XML MD5/HMAC-SHA256 双签名报文格式。
"""
import hashlib
import hmac
import re
from typing import Any, Dict, List, Optional, Tuple
import xml.sax.saxutils as saxutils

_XML_TAG_RE = re.compile(r"<([a-zA-Z0-9_]+)><!\[CDATA\[(.*?)\]\]></\1>|<([a-zA-Z0-9_]+)>([^<]*)</\3>", re.DOTALL)


def canonicalize_wx_params(params: Dict[str, Any]) -> str:
    """按字典序拼接非空参数（排除 sign 字段），生成微信 v2 待签名字符串。"""
    pairs: List[str] = []
    for k in sorted(params.keys()):
        if k == "sign":
            continue
        v = params[k]
        if v is None or str(v) == "":
            continue
        pairs.append(f"{k}={v}")
    return "&".join(pairs)


def sign_wx_v2_payload(params: Dict[str, Any], mch_api_key: str, sign_type: str = "MD5") -> str:
    base = canonicalize_wx_params(params)
    raw = f"{base}&key={mch_api_key}".encode("utf-8")
    if sign_type.upper() == "HMAC-SHA256":
        return hmac.new(mch_api_key.encode("utf-8"), raw, hashlib.sha256).hexdigest().upper()
    return hashlib.md5(raw).hexdigest().upper()


def verify_wx_v2_callback(xml_body: str, mch_api_key: str, sign_type: str = "MD5") -> Tuple[bool, Dict[str, str]]:
    parsed = parse_flat_wx_xml(xml_body)
    given_sign = parsed.get("sign", "")
    if not given_sign:
        return False, parsed
    expected = sign_wx_v2_payload(parsed, mch_api_key=mch_api_key, sign_type=sign_type)
    return hmac.compare_digest(given_sign.upper(), expected), parsed


def parse_flat_wx_xml(xml_body: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for m in _XML_TAG_RE.finditer(xml_body or ""):
        if m.group(1):
            out[m.group(1)] = m.group(2)
        elif m.group(3):
            out[m.group(3)] = saxutils.unescape(m.group(4))
    return out


def build_wx_unified_order_xml(
    app_id: str,
    mch_id: str,
    out_trade_no: str,
    total_fee_cents: int,
    body_desc: str,
    notify_url: str,
    nonce_str: str,
    mch_api_key: str,
    spbill_create_ip: str = "127.0.0.1",
) -> str:
    if int(total_fee_cents) <= 0:
        raise ValueError("total_fee_cents must be positive")
    payload: Dict[str, Any] = {
        "appid": app_id,
        "mch_id": mch_id,
        "nonce_str": nonce_str,
        "body": body_desc[:64],
        "out_trade_no": out_trade_no,
        "total_fee": int(total_fee_cents),
        "spbill_create_ip": spbill_create_ip,
        "notify_url": notify_url,
        "trade_type": "NATIVE",
    }
    payload["sign"] = sign_wx_v2_payload(payload, mch_api_key=mch_api_key, sign_type="HMAC-SHA256")
    lines = ["<xml>"]
    for k, v in payload.items():
        if isinstance(v, int):
            lines.append(f"  <{k}>{v}</{k}>")
        else:
            lines.append(f"  <{k}><![CDATA[{v}]]></{k}>")
    lines.append("</xml>")
    return "\n".join(lines)


def parse_wx_settlement_bill_csv(raw_csv: str) -> Dict[str, Any]:
    """解析微信支付每日资金账单（去除反引号前缀 ` 并汇总交易净额与手续费）。"""
    lines = [ln.strip() for ln in (raw_csv or "").splitlines() if ln.strip()]
    if len(lines) < 2:
        return {"records": [], "gross_cents": 0, "fee_cents": 0, "refund_cents": 0}

    headers = [h.strip().lstrip("`") for h in lines[0].split(",")]
    records: List[Dict[str, str]] = []
    gross_cents = 0
    fee_cents = 0
    refund_cents = 0

    for ln in lines[1:]:
        if ln.startswith("总交易单数") or ln.startswith("`总交易单数"):
            break
        cells = [c.strip().lstrip("`") for c in ln.split(",")]
        if len(cells) != len(headers):
            continue
        row = dict(zip(headers, cells))
        records.append(row)
        try:
            gross_cents += int(round(float(row.get("应结订单金额", "0") or 0) * 100))
            fee_cents += int(round(float(row.get("手续费", "0") or 0) * 100))
            refund_cents += int(round(float(row.get("申请退款金额", "0") or 0) * 100))
        except ValueError:
            continue

    return {
        "record_count": len(records),
        "gross_cents": gross_cents,
        "fee_cents": fee_cents,
        "refund_cents": refund_cents,
        "net_settlement_cents": gross_cents - refund_cents - fee_cents,
        "records": records,
    }


class WeChatRefundAdapterMock:
    """沙盒环境微信原路退费回执模拟器（供离线渠道退费测试使用，注意与站内钱包退费区分）。"""

    def __init__(self, mch_id: str = "1900008821"):
        self.mch_id = mch_id
        self._submitted: Dict[str, Dict[str, Any]] = {}

    def submit_channel_refund(
        self,
        out_trade_no: str,
        out_refund_no: str,
        total_fee_cents: int,
        refund_fee_cents: int,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        if refund_fee_cents <= 0 or refund_fee_cents > total_fee_cents:
            raise ValueError("Invalid channel refund amount")
        if out_refund_no in self._submitted:
            return dict(self._submitted[out_refund_no])
        rec = {
            "mch_id": self.mch_id,
            "out_trade_no": out_trade_no,
            "out_refund_no": out_refund_no,
            "total_fee_cents": int(total_fee_cents),
            "refund_fee_cents": int(refund_fee_cents),
            "result_code": "SUCCESS",
            "refund_desc": reason or "normal_refund",
        }
        self._submitted[out_refund_no] = rec
        return dict(rec)
