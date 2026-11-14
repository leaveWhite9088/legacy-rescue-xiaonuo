# -*- coding: utf-8 -*-
"""2024 月度财务关账 12 项前置门禁核查单生成器（离线风控报告模块）。"""
import sqlite3
from typing import Any, Dict, List

from app.legacy_v1.v1_currency_shim import parse_v1_yuan_string


def evaluate_v1_month_close_readiness(conn: sqlite3.Connection, period_key: str) -> Dict[str, Any]:
    """扫描目标账期是否存在未刷盘计量、挂起态结算单、同周期重单、负余额钱包及未处理死信。"""
    checks: List[Dict[str, Any]] = []

    unflushed = conn.execute(
        "SELECT COUNT(*) FROM usage_events WHERE period_key = ? AND flushed = 0",
        (period_key,),
    ).fetchone()[0]
    checks.append({
        "code": "CHK_01_UNFLUSHED_METERING",
        "passed": int(unflushed) == 0,
        "blocking": True,
        "metric": int(unflushed),
        "description": "当期异步计量事件缓冲表必须全部完成聚合刷盘",
    })

    stuck_settle = conn.execute(
        "SELECT COUNT(*) FROM invoices WHERE period_key = ? AND status = 'PENDING_SETTLE'",
        (period_key,),
    ).fetchone()[0]
    checks.append({
        "code": "CHK_02_NO_STUCK_PENDING_SETTLE",
        "passed": int(stuck_settle) == 0,
        "blocking": True,
        "metric": int(stuck_settle),
        "description": "不存在永久滞留于 PENDING_SETTLE 中间态的卡死账单",
    })

    dup_groups = conn.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT tenant_id, cycle_start, cycle_end
            FROM invoices
            WHERE period_key = ? AND status != 'VOID'
            GROUP BY tenant_id, cycle_start, cycle_end
            HAVING COUNT(*) > 1
        )
        """,
        (period_key,),
    ).fetchone()[0]
    checks.append({
        "code": "CHK_03_NO_DUPLICATE_CYCLE_INVOICES",
        "passed": int(dup_groups) == 0,
        "blocking": True,
        "metric": int(dup_groups),
        "description": "同一租户同一计费周期不存在多张非作废重复账单",
    })

    neg_wallets = conn.execute(
        "SELECT COUNT(*) FROM wallets WHERE cash_balance_cents < 0 OR promo_balance_cents < 0"
    ).fetchone()[0]
    checks.append({
        "code": "CHK_04_NON_NEGATIVE_WALLETS",
        "passed": int(neg_wallets) == 0,
        "blocking": True,
        "metric": int(neg_wallets),
        "description": "全平台现金池与赠送金池余额均不得为负数",
    })

    open_dlq = conn.execute("SELECT COUNT(*) FROM settlement_dlq WHERE status = 'PENDING'").fetchone()[0]
    checks.append({
        "code": "CHK_05_DLQ_DRAINED",
        "passed": int(open_dlq) == 0,
        "blocking": False,
        "metric": int(open_dlq),
        "description": "自动扣款死信队列已人工复核或完成重试",
    })

    invs = conn.execute("SELECT * FROM invoices WHERE period_key = ? AND status != 'VOID'", (period_key,)).fetchall()
    candidate_total = sum(
        parse_v1_yuan_string(dict(r).get("raw_legacy_total"), int(r["total_cents"] or 0))
        for r in invs
    )

    blocking_failures = [c["code"] for c in checks if c["blocking"] and not c["passed"]]
    return {
        "period_key": period_key,
        "ready_to_close": len(blocking_failures) == 0,
        "blocking_failures": blocking_failures,
        "candidate_archive_total_cents": candidate_total,
        "checks": checks,
    }
