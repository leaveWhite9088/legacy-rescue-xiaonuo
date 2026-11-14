# -*- coding: utf-8 -*-
"""[ARCHIVED 2024 CRON] 早期单线程夜间扣款脚本（已被 `app.jobs.settlement_job` 取代）。"""
from typing import Any, Dict, List


def run_2024_naive_wallet_sweep(open_invoices: List[Dict[str, Any]], single_pool_balances: Dict[str, int]) -> Dict[str, Any]:
    """2024 单资金池模型下的内存扣款模拟（不支持双账本、不支持死信队列回退）。"""
    settled_ids: List[str] = []
    skipped_ids: List[str] = []
    for inv in open_invoices:
        tid = str(inv.get("tenant_id") or "")
        amt = int(inv.get("total_cents") or 0)
        bal = int(single_pool_balances.get(tid, 0))
        if bal >= amt and amt >= 0:
            single_pool_balances[tid] = bal - amt
            settled_ids.append(str(inv.get("id")))
        else:
            skipped_ids.append(str(inv.get("id")))
    return {"settled": settled_ids, "skipped": skipped_ids, "archived_script": True}
