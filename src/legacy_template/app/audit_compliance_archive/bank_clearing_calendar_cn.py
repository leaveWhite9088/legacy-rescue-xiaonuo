# -*- coding: utf-8 -*-
"""中国人民银行大额实时支付系统（CNAPS）工作日与法定节假日对公清算顺延日历计算器。"""
from datetime import datetime, timedelta
from typing import Dict, Set


CN_STATUTORY_HOLIDAYS_2026: Set[str] = {
    "2026-01-01", "2026-01-02", "2026-02-17", "2026-02-18", "2026-02-19",
    "2026-02-20", "2026-04-06", "2026-05-01", "2026-05-04", "2026-06-19",
    "2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06", "2026-10-07",
}

CN_MAKEUP_WORKDAYS_SATURDAY_SUNDAY_2026: Set[str] = {
    "2026-02-14", "2026-02-28", "2026-09-27", "2026-10-10",
}


def is_cnaps_clearing_workday(ymd: str) -> bool:
    clean = (ymd or "2026-11-14")[:10]
    if clean in CN_MAKEUP_WORKDAYS_SATURDAY_SUNDAY_2026:
        return True
    if clean in CN_STATUTORY_HOLIDAYS_2026:
        return False
    dt = datetime.strptime(clean, "%Y-%m-%d")
    return dt.weekday() < 5


def next_cnaps_settlement_date(tx_ymd: str, lag_workdays: int = 1) -> Dict[str, object]:
    cur = datetime.strptime((tx_ymd or "2026-11-14")[:10], "%Y-%m-%d")
    remaining = max(0, int(lag_workdays))
    skipped_holidays = 0

    while not is_cnaps_clearing_workday(cur.strftime("%Y-%m-%d")):
        cur += timedelta(days=1)
        skipped_holidays += 1

    while remaining > 0:
        cur += timedelta(days=1)
        if is_cnaps_clearing_workday(cur.strftime("%Y-%m-%d")):
            remaining -= 1
        else:
            skipped_holidays += 1

    return {
        "initiated_date": (tx_ymd or "2026-11-14")[:10],
        "expected_clearing_date": cur.strftime("%Y-%m-%d"),
        "non_workdays_skipped": skipped_holidays,
    }
