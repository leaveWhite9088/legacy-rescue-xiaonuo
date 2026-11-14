#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""主控客观评分与脱敏事实卡提取器（支持三轮定性门禁微折计分 + 全链路分段计时）：
- build_fact_card(run_dir): 仅提取脱敏事实卡数据（供 judge_pack.py 盲评打包使用，不计算也不落盘最终得分）；
- score_run(run_dir, record=True): 执行权威客观打分（供 finalize.py 最终一键出榜定稿调用，按各轮冻结快照精确核算 1.0 / 0.9 / 0.8 轮次系数）。
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


def compute_t_score(elapsed_minutes: float, a_score: float, b_score: float, cfg: dict, round_timings: list | None = None) -> dict:
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
        "round_timings": round_timings or [],
        "T_raw": round(t_raw, 3),
        "quality_cap_ratio": round(quality_cap, 4),
        "T_score": round(t_final, 3),
    }


def _extract_anonymized_round_trace(run_dir: Path) -> list[dict]:
    rounds_dir = run_dir / "rounds"
    if not rounds_dir.exists():
        return []
    trace = []
    for rp in sorted(rounds_dir.glob("round-*.json")):
        try:
            rec = json.loads(rp.read_text(encoding="utf-8"))
            gk = rec.get("gatekeeper", {})
            trace.append(
                {
                    "round": int(rec.get("round", len(trace) + 1)),
                    "unit_tests_passed": bool(rec.get("unit_tests_passed", False)),
                    "all_closed": bool(gk.get("all_closed", False)),
                    "domains": [
                        {"domain": d["domain"], "status": d["status"]}
                        for d in gk.get("domains", [])
                    ],
                }
            )
        except Exception:
            pass
    return trace


def _write_fact_card(run_dir: Path, delivery_dir: Path, ab: dict, c: dict) -> dict:
    report_path = delivery_dir / "事故排查与处置说明.md"
    report_text = report_path.read_text(encoding="utf-8", errors="replace") if report_path.exists() else "（未提交排查说明）"
    fact_card = {
        "report_markdown": report_text,
        "rounds_trace": _extract_anonymized_round_trace(run_dir),
        "probe_summary": {
            "A1_bugs": {
                k: {"checks": [[chk[0], bool(chk[1])] for chk in v["checks"]]}
                for k, v in ab["A1_bugs"].items()
            },
            "A2_dirty_data": [[item[0], bool(item[1])] for item in ab["A2_checks"]],
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


def _check_passed_a1(ab_dict: dict, bid: str, idx: int, cname: str) -> bool:
    chks = ab_dict.get("A1_bugs", {}).get(bid, {}).get("checks", [])
    for item in chks:
        if item[0] == cname:
            return bool(item[1])
    if 0 <= idx < len(chks):
        return bool(chks[idx][1])
    return False


def _check_passed_a2(ab_dict: dict, cname: str) -> bool:
    for item in ab_dict.get("A2_checks", []):
        if item[0] == cname:
            return bool(item[1])
    return False


def _evaluate_with_round_discounts(run_dir: Path, final_ab: dict, proto: dict, cfg: dict) -> dict:
    mult_cfg = cfg.get("rounds", {}).get("multipliers", {"1": 1.0, "2": 0.9, "3": 0.8})
    m1 = float(mult_cfg.get("1", 1.0))
    m2 = float(mult_cfg.get("2", 0.9))
    m3 = float(mult_cfg.get("3", 0.8))

    final_sha = proto.get("integrity", {}).get("delivery_sha256", "")
    rounds_dir = run_dir / "rounds"
    r1_snap = rounds_dir / "round-01" / "snapshot"
    r2_snap = rounds_dir / "round-02" / "snapshot"
    r1_json = rounds_dir / "round-01.json"
    r2_json = rounds_dir / "round-02.json"

    if not r1_snap.exists():
        r1_ab = final_ab
        r2_ab = final_ab
    else:
        r1_sha = json.loads(r1_json.read_text(encoding="utf-8")).get("snapshot_sha256", "") if r1_json.exists() else ""
        if r1_sha and r1_sha == final_sha:
            r1_ab = final_ab
            r2_ab = final_ab
        else:
            r1_ab = run_eval(r1_snap)
            if not r2_snap.exists():
                r2_ab = final_ab
            else:
                r2_sha = json.loads(r2_json.read_text(encoding="utf-8")).get("snapshot_sha256", "") if r2_json.exists() else ""
                r2_ab = final_ab if (r2_sha and r2_sha == final_sha) else run_eval(r2_snap)

    discounted_a1 = {}
    for bid, binfo in final_ab["A1_bugs"].items():
        max_pts = float(binfo["max"])
        chks = binfo["checks"]
        per_chk = max_pts / max(1, len(chks))
        bug_score = 0.0
        chk_rows = []
        for idx, c_item in enumerate(chks):
            cname, ok_final = c_item[0], bool(c_item[1])
            if not ok_final:
                solved_round = None
                mult = 0.0
            elif _check_passed_a1(r1_ab, bid, idx, cname):
                solved_round = 1
                mult = m1
            elif _check_passed_a1(r2_ab, bid, idx, cname):
                solved_round = 2
                mult = m2
            else:
                solved_round = 3
                mult = m3
            bug_score += per_chk * mult
            chk_rows.append([cname, ok_final, solved_round, mult])
        discounted_a1[bid] = {
            "score": round(bug_score, 3),
            "raw_score": binfo["score"],
            "max": max_pts,
            "checks": chk_rows,
        }

    discounted_a2 = []
    a2_score_sum = 0.0
    for item in final_ab["A2_checks"]:
        cname, ok_final, pts = item[0], bool(item[1]), float(item[2])
        if not ok_final:
            solved_round = None
            mult = 0.0
            earned = 0.0
        elif _check_passed_a2(r1_ab, cname):
            solved_round = 1
            mult = m1
            earned = pts * m1
        elif _check_passed_a2(r2_ab, cname):
            solved_round = 2
            mult = m2
            earned = pts * m2
        else:
            solved_round = 3
            mult = m3
            earned = pts * m3
        a2_score_sum += earned
        discounted_a2.append([cname, ok_final, pts, solved_round, mult, round(earned, 3)])

    a1_final = round(sum(v["score"] for v in discounted_a1.values()), 3)
    a2_final = round(a2_score_sum, 3)
    return {
        "A1_score": a1_final,
        "A1_raw_score": final_ab["A1_score"],
        "A2_score": a2_final,
        "A2_raw_score": final_ab["A2_score"],
        "A_score": round(a1_final + a2_final, 3),
        "A_raw_score": final_ab["A_score"],
        "A1_bugs": discounted_a1,
        "A2_checks": discounted_a2,
    }


def score_run(run_dir: Path, record: bool = True) -> dict:
    """根据冻结交付快照、轮次门禁快照与计时协议重新计算权威 A/B/C/T 客观分。"""
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    proto_path = run_dir / "protocol.json"
    if not proto_path.exists():
        raise FileNotFoundError(f"找不到封包协议文件: {proto_path}")
    proto = json.loads(proto_path.read_text(encoding="utf-8"))
    delivery_dir = run_dir / "delivery"
    if not delivery_dir.exists():
        raise FileNotFoundError(f"找不到交付目录: {delivery_dir}")

    final_ab = run_eval(delivery_dir)
    disc_a = _evaluate_with_round_discounts(run_dir, final_ab, proto, cfg)
    c = run_code_audit(delivery_dir)
    elapsed_min = float(proto["timing"]["elapsed_minutes"])
    round_timings = proto["timing"].get("round_timings", [])
    t = compute_t_score(elapsed_min, disc_a["A_score"], final_ab["B_score"], cfg, round_timings=round_timings)

    penalty_factor = 0.7 if final_ab["severe_flags"] else 1.0
    objective_raw = disc_a["A_score"] + final_ab["B_score"] + c["C_score"] + t["T_score"]
    objective_final = round(objective_raw * penalty_factor, 3)

    result = {
        "run_id": proto["run_id"],
        "model": proto["model"],
        "canonical_model": proto["canonical_model"],
        "objective_score": objective_final,
        "objective_max": 80.0,
        "penalty_factor": penalty_factor,
        "A_score": disc_a["A_score"],
        "A_raw_score": disc_a["A_raw_score"],
        "A1_score": disc_a["A1_score"],
        "A1_raw_score": disc_a["A1_raw_score"],
        "A2_score": disc_a["A2_score"],
        "A2_raw_score": disc_a["A2_raw_score"],
        "B_score": final_ab["B_score"],
        "C_score": c["C_score"],
        "C1_score": c["C1_score"],
        "C2_score": c["C2_score"],
        "T_score": t["T_score"],
        "rounds_completed": int(proto.get("diagnostics", {}).get("rounds_completed", len(round_timings))),
        "timing": t,
        "severe_flags": final_ab["severe_flags"],
        "details": {
            "A1_bugs": disc_a["A1_bugs"],
            "A2_checks": disc_a["A2_checks"],
            "B_checks": final_ab["B_checks"],
            "diff_stats": c["diff_stats"],
            "mutation_tests": c["mutation_tests"],
        },
        "diagnostics": proto.get("diagnostics", {}),
    }

    _write_fact_card(run_dir, delivery_dir, final_ab, c)
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
        f"(A={res['A_score']}/35 [原始{res['A_raw_score']}], B={res['B_score']}/20, "
        f"C={res['C_score']}/10, T={res['T_score']}/15, 耗时={res['timing']['elapsed_minutes']}m, 门禁轮次={res['rounds_completed']})"
    )
    if res["severe_flags"]:
        print("严重违规标记:", ", ".join(res["severe_flags"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
