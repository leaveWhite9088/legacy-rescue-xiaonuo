# -*- coding: utf-8 -*-
"""[ARCHIVED 2024 CRON] 2024 夜间 PostScript 对账单打印队列生成脚本。"""
from typing import Dict, List


def build_2024_spool_queue_manifest(invoice_ids: List[str], batch_date: str = "2024-12-31") -> List[Dict[str, str]]:
    return [
        {
            "spool_job_id": f"SPL-{batch_date.replace('-', '')}-{idx:04d}",
            "invoice_id": inv_id,
            "target_Filename": f"statement_{inv_id}.ps",
        }
        for idx, inv_id in enumerate(invoice_ids, start=1)
    ]
