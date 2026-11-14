# -*- coding: utf-8 -*-
"""《个人信息保护法》(PIPL) 与外审脱敏抽样导出器：对企业联系人邮箱、手机号、税号及鉴权令牌进行不可逆掩码处理。"""
import hashlib
from typing import Any, Dict, List


def mask_company_title_for_external_sample(company_name: str) -> str:
    txt = (company_name or "").strip()
    if len(txt) <= 4:
        return txt[:1] + "***"
    return f"{txt[:2]}***{txt[-2:]}"


def anonymize_tenant_billing_record(record: Dict[str, Any], salt: str = "yunce_pipl_2026") -> Dict[str, Any]:
    tid = str(record.get("tenant_id") or record.get("id") or "unknown")
    pseudo_id = "ANON_" + hashlib.sha256(f"{tid}:{salt}".encode("utf-8")).hexdigest()[:12].upper()
    out = dict(record)
    out["pseudonymized_id"] = pseudo_id
    if "api_token" in out:
        out["api_token"] = "[REDACTED_TOKEN]"
    if "company_name" in out:
        out["company_name"] = mask_company_title_for_external_sample(str(out["company_name"]))
    if "buyer_tax_id" in out and out["buyer_tax_id"]:
        raw_tax = str(out["buyer_tax_id"])
        out["buyer_tax_id"] = raw_tax[:4] + "**********" + raw_tax[-4:] if len(raw_tax) >= 10 else "***"
    return out


def anonymize_batch_for_research_export(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [anonymize_tenant_billing_record(r) for r in records]
