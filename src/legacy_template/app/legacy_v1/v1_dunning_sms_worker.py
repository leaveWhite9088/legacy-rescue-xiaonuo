# -*- coding: utf-8 -*-
"""2024 旧版催收短信与邮件模板渲染器（已被 v2 dunning_engine 取代，保留模板常量）。"""
from typing import Any, Dict, List
import sqlite3

from app.legacy_v1.v1_currency_shim import format_v1_yuan_display

SMS_TEMPLATES_2024 = {
    "T_MINUS_3": "【云策企服】尊敬的{company}，贵司账单{inv_id}（金额{amount}）将于3日后到期，请及时确保钱包余额充足。",
    "OVERDUE_DAY_1": "【云策企服】尊敬的{company}，贵司账单{inv_id}已逾期1天，未结金额{amount}，请尽快充值以免产生5%滞纳金。",
    "OVERDUE_DAY_7": "【云策企服】紧急提醒：{company}账单{inv_id}逾期已满7天，含滞纳金应付{amount}，超15天将触发API限流。",
    "OVERDUE_DAY_15": "【云策企服】停服预警：{company}名下账单{inv_id}严重逾期，系统已进入配额只读保护状态，请联系客户经理。",
}


def build_v1_dunning_preview_batches(conn: sqlite3.Connection, period_key: str) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT i.id, i.tenant_id, i.total_cents, i.paid_cents, i.late_fee_cents, i.status, t.company_name
        FROM invoices i
        JOIN tenants t ON t.id = i.tenant_id
        WHERE i.period_key = ? AND i.status IN ('OPEN', 'PENDING_SETTLE')
        ORDER BY i.total_cents DESC
        """,
        (period_key,),
    ).fetchall()

    batches: List[Dict[str, Any]] = []
    for r in rows:
        unpaid = max(0, int(r["total_cents"]) - int(r["paid_cents"]))
        if unpaid <= 0:
            continue
        tpl_key = "OVERDUE_DAY_7" if int(r["late_fee_cents"]) > 0 else "T_MINUS_3"
        msg = SMS_TEMPLATES_2024[tpl_key].format(
            company=r["company_name"],
            inv_id=r["id"],
            amount=format_v1_yuan_display(unpaid),
        )
        batches.append({
            "invoice_id": r["id"],
            "tenant_id": r["tenant_id"],
            "template_key": tpl_key,
            "unpaid_cents": unpaid,
            "rendered_sms": msg,
        })
    return batches
