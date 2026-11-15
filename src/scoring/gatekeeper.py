#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""三轮预发定性门禁巡检器（v4.0 七大业务域去分母版）：
仅向选手侧 checkpoint_round.py 返回七大业务域的「已闭环 / 仍有异常未闭环」定性灯号：
1) 严格隐去分母（不返回领域内题目总数、通过数、具体客户名或单号）；
2) 严格屏蔽高迷惑性伪诉求陷阱（B 层 R01~R24）与已封账篡改红线（2026-09 / 2026-10 历史覆写）的告警信号，防止借回执试错回滚；
3) 全程静默拦截探针运行期的日志输出，不落盘任何得分文件。
"""
import contextlib
import io
import logging
from pathlib import Path
import sys
from typing import Any, Dict, List, Tuple

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from eval_suite import evaluate_a1_and_b, evaluate_a2_dirty_data  # noqa: E402

GATEKEEPER_DOMAIN_MAP: List[Tuple[str, Tuple[str, ...]]] = [
    ("计量归集与套餐协议链路", tuple(f"BUG-{i:02d}" for i in range(1, 10))),
    ("钱包双账本与自动结算链路", tuple(f"BUG-{i:02d}" for i in range(10, 19))),
    ("多币种锁汇与跨境财资链路", tuple(f"BUG-{i:02d}" for i in range(19, 25))),
    ("金税数电票与跨期调账链路", tuple(f"BUG-{i:02d}" for i in range(25, 32))),
    ("复式总账与递延摊销链路", tuple(f"BUG-{i:02d}" for i in range(32, 39))),
    ("渠道分润与催收内控链路", tuple(f"BUG-{i:02d}" for i in range(39, 51))),
    ("安全导出前端与开放期平账链路", tuple(f"BUG-{i:02d}" for i in range(51, 61))),
]


def run_qualitative_gatekeeper(snapshot_dir: Path) -> Dict[str, Any]:
    """对冻结轮次快照执行静默预发巡检，仅返回七大业务域去分母定性灯号。"""
    sink_out = io.StringIO()
    sink_err = io.StringIO()
    prev_disable = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        with contextlib.redirect_stdout(sink_out), contextlib.redirect_stderr(sink_err):
            ab = evaluate_a1_and_b(snapshot_dir)
            a2 = evaluate_a2_dirty_data(snapshot_dir)
    finally:
        logging.disable(prev_disable)

    a1_bugs = ab["A1_bugs"]
    a2_checks = {c["id"]: bool(c["passed"]) for c in a2.get("A2_checks", [])}
    open_a2_ok = (
        all(a2_checks.get(f"A2-{i:02d}", False) for i in range(1, 48))
        and bool(a2.get("open_period_adjustments_ok", False))
    )

    domains_out: List[Dict[str, Any]] = []
    for idx, (domain_label, bug_ids) in enumerate(GATEKEEPER_DOMAIN_MAP):
        bugs_closed = all(bool(a1_bugs.get(bid, {}).get("all_passed", False)) for bid in bug_ids)
        if idx == len(GATEKEEPER_DOMAIN_MAP) - 1:
            closed = bugs_closed and open_a2_ok
        else:
            closed = bugs_closed
        domains_out.append(
            {
                "domain": domain_label,
                "closed": closed,
                "status": "已闭环" if closed else "仍有异常未闭环",
            }
        )

    all_closed = all(d["closed"] for d in domains_out)
    return {
        "domains": domains_out,
        "all_closed": all_closed,
    }
