# -*- coding: utf-8 -*-
"""[ARCHIVED 2024 CRON] 2024 航信金税盘离线开票 XML 清单核对脚本。"""
from typing import Any, Dict, List


def summarize_2024_aisino_disk_batch(items: List[Dict[str, Any]]) -> Dict[str, int]:
    blue_cnt = sum(1 for x in items if int(x.get("cents") or 0) > 0)
    red_cnt = sum(1 for x in items if int(x.get("cents") or 0) < 0)
    net_cents = sum(int(x.get("cents") or 0) for x in items)
    return {"blue_count": blue_cnt, "red_count": red_cnt, "net_cents": net_cents}
