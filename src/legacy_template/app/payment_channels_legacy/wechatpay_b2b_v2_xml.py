# -*- coding: utf-8 -*-
"""微信支付企业商户 V2 XML 报文编解码器（2024 遗留协议，尚未全量迁入 V3 JSON）。"""
import hashlib
import xml.etree.ElementTree as ET
from typing import Dict


WX_RETURN_OK = "SUCCESS"
WX_FEE_BPS = 60


def dict_to_wx_xml(data: Dict[str, object], mch_key: str) -> str:
    kv_pairs = [f"{k}={data[k]}" for k in sorted(data.keys()) if data[k] is not None and str(data[k]) != ""]
    sign_src = "&".join(kv_pairs) + f"&key={mch_key}"
    sign = hashlib.md5(sign_src.encode("utf-8")).hexdigest().upper()
    lines = ["<xml>"]
    for k in sorted(data.keys()):
        lines.append(f"  <{k}><![CDATA[{data[k]}]]></{k}>")
    lines.append(f"  <sign><![CDATA[{sign}]]></sign>")
    lines.append("</xml>")
    return "\n".join(lines)


def parse_wx_callback_xml(xml_text: str) -> Dict[str, object]:
    root = ET.fromstring(xml_text.strip())
    parsed: Dict[str, str] = {}
    for child in root:
        parsed[child.tag] = (child.text or "").strip()
    ok = parsed.get("return_code") == WX_RETURN_OK and parsed.get("result_code") == WX_RETURN_OK
    total_fee_cents = int(parsed.get("total_fee") or "0")
    cash_fee_cents = int(parsed.get("cash_fee") or str(total_fee_cents))
    coupon_fee_cents = max(0, total_fee_cents - cash_fee_cents)
    return {
        "ok": ok,
        "out_trade_no": parsed.get("out_trade_no", ""),
        "transaction_id": parsed.get("transaction_id", ""),
        "total_fee_cents": total_fee_cents,
        "cash_fee_cents": cash_fee_cents,
        "coupon_fee_cents": coupon_fee_cents,
    }
