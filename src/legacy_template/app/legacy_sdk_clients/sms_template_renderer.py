# -*- coding: utf-8 -*-
"""运营商报备签名短信模板渲染器（严禁在催收或余额提醒短信中拼接未转义外部链接）。"""
from typing import Dict


APPROVED_SMS_TEMPLATES: Dict[str, str] = {
    "SMS_QUOTA_80": "【云策计费】尊敬的{company}，您当月套餐配额已使用{pct}%，请留意调用水位。",
    "SMS_INVOICE_DUE": "【云策计费】尊敬的{company}，账单{invoice_id}（人民币{yuan}元）即将到期，请及时充值核销。",
    "SMS_PROMO_EXPIRING": "【云策计费】您账户内有{yuan}元赠送金将于{date}到期清零，请合理安排调用。",
}


def render_approved_sms(template_code: str, params: Dict[str, object]) -> str:
    tpl = APPROVED_SMS_TEMPLATES.get(template_code)
    if not tpl:
        raise KeyError(f"Unregistered SMS template: {template_code}")
    safe_params = {k: str(v).replace("http://", "").replace("https://", "") for k, v in params.items()}
    return tpl.format(**safe_params)
