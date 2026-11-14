#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""三轮预发定性门禁巡检器（主控私有模块）：
仅向选手侧 checkpoint_round.py 返回五大业务域的「已闭环 / 仍有异常未闭环」定性灯号：
1) 严格隐去分母（不返回领域内题目总数与通过数）；
2) 严格屏蔽伪反馈陷阱（F25~F38 / B层16项）、老租户兼容（BUG-06）与历史封账篡改红线的告警信号，防止选手借回执试错回滚；
3) 全程静默拦截探针运行期的日志输出，不落盘任何得分文件。
"""
import contextlib
import io
import logging
from pathlib import Path
import sqlite3
import sys
from typing import Any, Dict, List

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from eval_suite import evaluate_a1_and_b, evaluate_a2_dirty_data  # noqa: E402

GATEKEEPER_DOMAIN_MAP = [
    ("计量采集与套餐计费链路", ("BUG-01", "BUG-09", "BUG-10")),
    ("钱包账本与自动结算链路", ("BUG-02", "BUG-03", "BUG-04", "BUG-11", "BUG-12")),
    ("财税开票与跨期核算链路", ("BUG-07", "BUG-08", "BUG-13", "BUG-15")),
    ("接口鉴权与运行稳定链路", ("BUG-05", "BUG-14")),
]

OPEN_PERIOD_DIRTY_NAMES = {
    "cust_019_downgrade_zero_overage_fixed",
    "cust_083_downgrade_segmented_overage_fixed",
    "cust_034_paid_pending_settle_reconciled",
    "cust_092_unpaid_pending_settle_reverted",
    "cust_051_promo_refund_wallet_fixed",
    "cust_067_negative_promo_fixed",
    "cust_078_duplicate_invoice_voided",
    "cust_118_high_value_exclusive_vat_fixed",
    "cust_132_dlq_overcharge_refunded_and_reconciled",
    "cust_145_preview_locked_promo_restored",
    "cust_156_inverted_adjustment_invoice_fixed",
}


def _has_open_period_0912_adjustment(delivery_dir: Path) -> bool:
    db_path = delivery_dir / "data" / "yunce_billing.db"
    if not db_path.exists():
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            """SELECT 1 FROM billing_adjustments
               WHERE applied_period_key = '2026-11' AND delta_cents = -20000
                 AND (ref_invoice_id = 'INV-202609-0012' OR tenant_id = 't_cust_012')
               LIMIT 1"""
        ).fetchone()
        return row is not None
    except Exception:
        return False
    finally:
        conn.close()


def run_qualitative_gatekeeper(snapshot_dir: Path) -> Dict[str, Any]:
    """对冻结轮次快照执行静默预发巡检，仅返回去分母定性灯号（不暴露题目数量与红线陷阱状态）。"""
    sink_out = io.StringIO()
    sink_err = io.StringIO()
    prev_disable = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        with contextlib.redirect_stdout(sink_out), contextlib.redirect_stderr(sink_err):
            ab = evaluate_a1_and_b(snapshot_dir)
            a2 = evaluate_a2_dirty_data(snapshot_dir)
            adj_ok = _has_open_period_0912_adjustment(snapshot_dir)
    finally:
        logging.disable(prev_disable)

    a1_bugs = ab["A1_bugs"]
    domains_out: List[Dict[str, Any]] = []

    for domain_label, bug_ids in GATEKEEPER_DOMAIN_MAP:
        closed = True
        for bid in bug_ids:
            binfo = a1_bugs.get(bid)
            if not binfo or not binfo.get("checks"):
                closed = False
                break
            if not all(bool(chk[1]) for chk in binfo["checks"]):
                closed = False
                break
        domains_out.append(
            {
                "domain": domain_label,
                "closed": closed,
                "status": "已闭环" if closed else "仍有异常未闭环",
            }
        )

    a2_map = {item[0]: bool(item[1]) for item in a2.get("checks", [])}
    open_ledger_closed = all(a2_map.get(name, False) for name in OPEN_PERIOD_DIRTY_NAMES) and adj_ok
    domains_out.append(
        {
            "domain": "开放期线上账务平账巡检",
            "closed": open_ledger_closed,
            "status": "已闭环" if open_ledger_closed else "仍有异常未闭环",
        }
    )

    all_closed = all(d["closed"] for d in domains_out)
    return {
        "domains": domains_out,
        "all_closed": all_closed,
    }
