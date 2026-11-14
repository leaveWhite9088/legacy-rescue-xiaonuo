#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""主控客观评分与脱敏事实卡提取器：
- build_fact_card(run_dir): 仅提取脱敏事实卡数据（供 judge_pack.py 盲评打包使用，不落盘最终得分）；
- score_run(run_dir, record=True): 执行权威客观打分（供 finalize.py 最终一键出榜定稿或开发自检使用）。
"""
import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))

from code_audit import run_code_audit  # noqa: E402
from eval_suite import run_eval  # noqa: E402

CONFIG_PATH = ROOT / "configs" / "benchmark.json"


def compute_t_score(elapsed_minutes: float, a_score: float, b_score: float, cfg: dict) -> dict:
    t_cfg = cfg["timing"]
    m = float(t_cfg["full_score_minutes"])
    h = float(t_cfg["half_life_minutes"])
    max_s = float(t_cfg["max_score"])

    if elapsed_minutes <= m:
        t_raw = max_s
    else:
        t_raw = max_s * (0.5 ** ((elapsed_minutes - m) / h))

    quality_cap = max(0.0, (a_score / 35.0) * (b_score / 20.0))
    t_final = min(t_raw, max_s * quality_cap)
    return {
        "elapsed_minutes": round(elapsed_minutes, 3),
        "T_raw": round(t_raw, 3),
        "quality_cap_ratio": round(quality_cap, 4),
        "T_score": round(t_final, 3),
    }


def _write_fact_card(run_dir: Path, delivery_dir: Path, ab: dict, c: dict) -> dict:
    report_path = delivery_dir / "事故排查与处置说明.md"
    report_text = report_path.read_text(encoding="utf-8", errors="replace") if report_path.exists() else "（未提交排查说明）"
    fact_card = {
        "report_markdown": report_text,
        "probe_summary": {
            "A1_bugs": {
                k: {"checks": v["checks"]} for k, v in ab["A1_bugs"].items()
            },
            "A2_dirty_data": [[item[0], item[1]] for item in ab["A2_checks"]],
            "B_regression": ab["B_checks"],
            "severe_flags": ab["severe_flags"],
        },
        "code_changes": c["diff_stats"],
        "mutation_tests": {
            "tested_files": c["mutation_tests"].get("tested_files", []),
        },
    }
    (run_dir / "事实卡数据.json").write_text(
        json.dumps(fact_card, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return fact_card


def build_fact_card(run_dir: Path) -> dict:
    """仅运行探针生成匿名盲评所需的《事实卡数据.json》，不计算或落盘最终客观分数。"""
    delivery_dir = run_dir / "delivery"
    if not delivery_dir.exists():
        raise FileNotFoundError(f"找不到交付目录: {delivery_dir}")
    ab = run_eval(delivery_dir)
    c = run_code_audit(delivery_dir)
    return _write_fact_card(run_dir, delivery_dir, ab, c)


def score_run(run_dir: Path, record: bool = True) -> dict:
    """根据冻结交付快照与计时协议重新计算权威 A/B/C/T 客观分。"""
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    proto_path = run_dir / "protocol.json"
    if not proto_path.exists():
        raise FileNotFoundError(f"找不到封包协议文件: {proto_path}")
    proto = json.loads(proto_path.read_text(encoding="utf-8"))
    delivery_dir = run_dir / "delivery"
    if not delivery_dir.exists():
        raise FileNotFoundError(f"找不到交付目录: {delivery_dir}")

    ab = run_eval(delivery_dir)
    c = run_code_audit(delivery_dir)
    elapsed_min = float(proto["timing"]["elapsed_minutes"])
    t = compute_t_score(elapsed_min, ab["A_score"], ab["B_score"], cfg)

    penalty_factor = 0.7 if ab["severe_flags"] else 1.0
    objective_raw = ab["A_score"] + ab["B_score"] + c["C_score"] + t["T_score"]
    objective_final = round(objective_raw * penalty_factor, 3)

    result = {
        "run_id": proto["run_id"],
        "model": proto["model"],
        "canonical_model": proto["canonical_model"],
        "objective_score": objective_final,
        "objective_max": 80.0,
        "penalty_factor": penalty_factor,
        "A_score": ab["A_score"],
        "A1_score": ab["A1_score"],
        "A2_score": ab["A2_score"],
        "B_score": ab["B_score"],
        "C_score": c["C_score"],
        "C1_score": c["C1_score"],
        "C2_score": c["C2_score"],
        "T_score": t["T_score"],
        "timing": t,
        "severe_flags": ab["severe_flags"],
        "details": {
            "A1_bugs": ab["A1_bugs"],
            "A2_checks": ab["A2_checks"],
            "B_checks": ab["B_checks"],
            "diff_stats": c["diff_stats"],
            "mutation_tests": c["mutation_tests"],
        },
        "diagnostics": proto.get("diagnostics", {}),
    }

    _write_fact_card(run_dir, delivery_dir, ab, c)
    if record:
        (run_dir / "评分.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="对单次交付 run 执行 A/B/C/T 客观评分（开发自检或 finalize 内部调用）")
    ap.add_argument("run_dir", help="runs/<run_id> 目录路径")
    ap.add_argument("--no-record", action="store_true", help="只打印与更新事实卡，不落盘 评分.json")
    args = ap.parse_args()

    res = score_run(Path(args.run_dir).resolve(), record=not args.no_record)
    print(
        f"[{res['run_id']}] 客观总分={res['objective_score']}/80 "
        f"(A={res['A_score']}/35, B={res['B_score']}/20, C={res['C_score']}/10, T={res['T_score']}/15)"
    )
    if res["severe_flags"]:
        print("严重违规标记:", ", ".join(res["severe_flags"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
