#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""主控客观评分与脱敏事实卡提取器（v4.0 严格梯度版）：
- build_fact_card(run_dir): 仅提取脱敏事实卡数据与客观覆盖率锚点（供 judge_pack.py 盲评打包使用，不计算也不落盘最终得分）；
- score_run(run_dir, record=True): 执行权威客观打分（供 finalize.py 最终一键出榜定稿调用，按单题 All-or-Nothing 与 1.00 / 0.85 / 0.70 轮次阶梯系数核算）。
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))

from code_audit import run_code_audit  # noqa: E402
from eval_suite import run_eval  # noqa: E402

CONFIG_PATH = ROOT / "configs" / "benchmark.json"


def compute_scoring_fingerprint() -> str:
    """计算当前评分配置与客观评分脚本的指纹，用于判断已落盘 评分.json 是否可直接复用。"""
    h = hashlib.sha256()
    for p in (CONFIG_PATH, HERE / "eval_suite.py", HERE / "code_audit.py", HERE / "score_delivery.py"):
        if p.exists():
            h.update(p.name.encode("utf-8"))
            h.update(p.read_bytes())
    return h.hexdigest()


def compute_t_score(
    elapsed_minutes: float,
    a_score: float,
    b_score: float,
    cfg: dict,
    round_timings: list | None = None,
) -> dict:
    t_cfg = cfg["timing"]
    m = float(t_cfg["full_score_minutes"])
    h = float(t_cfg["half_life_minutes"])
    max_s = float(t_cfg["max_score"])
    a_exp = float(t_cfg.get("quality_a_exponent", 1.2))

    if elapsed_minutes <= m:
        t_raw = max_s
    else:
        t_raw = max_s * (0.5 ** ((elapsed_minutes - m) / h))

    weights_cfg = cfg.get("weights", {})
    a_max = float(weights_cfg.get("A_root_cause_and_ledger", 35.0))
    b_max = float(weights_cfg.get("B_regression_protection", 20.0))
    a_ratio = max(0.0, min(1.0, a_score / a_max))
    b_ratio = max(0.0, min(1.0, 1.0 + b_score / 24.0)) if b_max <= 0 else max(0.0, min(1.0, b_score / b_max))
    quality_cap = (a_ratio ** a_exp) * b_ratio
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
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    silent_ids = {b["id"] for b in cfg.get("bugs", []) if b.get("silent")}

    report_path = delivery_dir / "事故排查与处置说明.md"
    report_text = report_path.read_text(encoding="utf-8", errors="replace") if report_path.exists() else "（未提交排查说明）"

    a1_bugs = ab["A1"]["bugs"]
    a2_checks = ab["A2"]["checks"]
    b_checks = ab["B"]["checks"]

    a1_passed_cnt = sum(1 for v in a1_bugs.values() if v.get("all_passed"))
    silent_passed_cnt = sum(1 for bid in silent_ids if a1_bugs.get(bid, {}).get("all_passed"))
    a2_passed_cnt = sum(1 for item in a2_checks if item.get("passed"))
    b_passed_cnt = sum(1 for item in b_checks if item.get("passed"))

    cited_f = {
        f"F{int(m):02d}"
        for m in re.findall(r"\bF(0?[1-9]|[1-5][0-9]|6[0-8])\b", report_text)
    }

    fact_card = {
        "report_markdown": report_text,
        "rounds_trace": _extract_anonymized_round_trace(run_dir),
        "coverage_anchors": {
            "a1_passed": a1_passed_cnt,
            "a1_total": len(a1_bugs),
            "silent_passed": silent_passed_cnt,
            "silent_total": len(silent_ids),
            "a2_passed": a2_passed_cnt,
            "a2_total": len(a2_checks),
            "b_passed": b_passed_cnt,
            "b_total": len(b_checks),
            "c2_valid_methods": int(c["mutation_tests"].get("valid_catching_methods_count", 0)),
            "c2_required_methods": int(c["mutation_tests"].get("required_catching_methods", 18)),
            "dead_code_files_count": int(c["diff_stats"].get("dead_code_files_count", 0)),
            "f_items_cited": len(cited_f),
            "f_items_total": 68,
        },
        "probe_summary": {
            "A1_bugs": {
                k: {
                    "all_passed": bool(v.get("all_passed")),
                    "silent": k in silent_ids,
                    "checks": [[chk[0], bool(chk[1])] for chk in v["checks"]],
                }
                for k, v in sorted(a1_bugs.items())
            },
            "A2_dirty_data": [[f"{item['id']}:{item['name']}", bool(item["passed"])] for item in a2_checks],
            "B_regression": b_checks,
            "severe_flags": ab["severe_flags"],
        },
        "code_changes": c["diff_stats"],
        "mutation_tests": {
            "valid_catching_methods_count": int(c["mutation_tests"].get("valid_catching_methods_count", 0)),
            "required_catching_methods": int(c["mutation_tests"].get("required_catching_methods", 18)),
            "tested_files": c["mutation_tests"].get("tested_files", []),
            "tested_methods": c["mutation_tests"].get("tested_methods", []),
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


def _bug_unit_passed(ab_dict: dict, bid: str) -> bool:
    return bool(ab_dict.get("A1", {}).get("bugs", {}).get(bid, {}).get("all_passed", False))


def _a2_item_passed(ab_dict: dict, cid: str) -> bool:
    for item in ab_dict.get("A2", {}).get("checks", []):
        if item.get("id") == cid:
            return bool(item.get("passed", False))
    return False


def _evaluate_with_round_discounts(run_dir: Path, final_ab: dict, proto: dict, cfg: dict) -> dict:
    mult_cfg = cfg.get("rounds", {}).get("multipliers", {"1": 1.0, "2": 0.85, "3": 0.7})
    m1 = float(mult_cfg.get("1", 1.0))
    m2 = float(mult_cfg.get("2", 0.85))
    m3 = float(mult_cfg.get("3", 0.7))

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
    a1_score_sum = 0.0
    for bid, binfo in sorted(final_ab["A1"]["bugs"].items()):
        max_pts = float(binfo["max"])
        ok_final = bool(binfo.get("all_passed", False))
        if not ok_final:
            solved_round = None
            mult = 0.0
            bug_score = 0.0
        elif _bug_unit_passed(r1_ab, bid):
            solved_round = 1
            mult = m1
            bug_score = max_pts * m1
        elif _bug_unit_passed(r2_ab, bid):
            solved_round = 2
            mult = m2
            bug_score = max_pts * m2
        else:
            solved_round = 3
            mult = m3
            bug_score = max_pts * m3
        a1_score_sum += bug_score

        discounted_a1[bid] = {
            "score": round(bug_score, 4),
            "raw_score": float(binfo["score"]),
            "max": max_pts,
            "all_passed": ok_final,
            "solved_round": solved_round,
            "multiplier": mult,
            "checks": [[c_item[0], bool(c_item[1])] for c_item in binfo["checks"]],
        }

    discounted_a2 = []
    a2_score_sum = 0.0
    for item in final_ab["A2"]["checks"]:
        cid = item["id"]
        cname = item["name"]
        ok_final = bool(item["passed"])
        pts = float(item["max"])
        if not ok_final:
            solved_round = None
            mult = 0.0
            earned = 0.0
        elif _a2_item_passed(r1_ab, cid):
            solved_round = 1
            mult = m1
            earned = pts * m1
        elif _a2_item_passed(r2_ab, cid):
            solved_round = 2
            mult = m2
            earned = pts * m2
        else:
            solved_round = 3
            mult = m3
            earned = pts * m3
        a2_score_sum += earned
        discounted_a2.append(
            {
                "id": cid,
                "name": cname,
                "passed": ok_final,
                "max": pts,
                "solved_round": solved_round,
                "multiplier": mult,
                "score": round(earned, 4),
            }
        )

    a1_final = round(a1_score_sum, 3)
    a2_final = round(a2_score_sum, 3)
    weights_cfg = cfg.get("weights", {})
    a1_max = float(weights_cfg.get("A1_bugs", 45.0))
    a2_max = float(weights_cfg.get("A2_dirty_data", 17.0))
    a1_exp = float(weights_cfg.get("a1_convex_exponent", 1.0))
    a2_exp = float(weights_cfg.get("a2_convex_exponent", 1.0))
    if a1_max > 0 and a1_exp != 1.0:
        a1_final = round(a1_max * (max(0.0, min(1.0, a1_final / a1_max)) ** a1_exp), 3)
    if a2_max > 0 and a2_exp != 1.0:
        a2_final = round(a2_max * (max(0.0, min(1.0, a2_final / a2_max)) ** a2_exp), 3)
    a1_raw = float(final_ab["A1"]["score"])
    a2_raw = float(final_ab["A2"]["score"])
    return {
        "A1_score": a1_final,
        "A1_raw_score": a1_raw,
        "A2_score": a2_final,
        "A2_raw_score": a2_raw,
        "A_score": round(a1_final + a2_final, 3),
        "A_raw_score": round(a1_raw + a2_raw, 3),
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
    b_score = float(final_ab["B"]["score"])
    t = compute_t_score(elapsed_min, disc_a["A_score"], b_score, cfg, round_timings=round_timings)

    severe_pen = float(cfg.get("regression", {}).get("severe_penalty_factor", 0.65))
    penalty_factor = severe_pen if final_ab["severe_flags"] else 1.0
    objective_raw = disc_a["A_score"] + b_score + c["C_score"] + t["T_score"]
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
        "B_score": b_score,
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
            "B_checks": final_ab["B"]["checks"],
            "diff_stats": c["diff_stats"],
            "mutation_tests": c["mutation_tests"],
        },
        "diagnostics": proto.get("diagnostics", {}),
        "cache_meta": {
            "fingerprint": compute_scoring_fingerprint(),
            "delivery_sha256": str(proto.get("integrity", {}).get("delivery_sha256", "")),
        },
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
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    w = cfg.get("weights", {})
    print(
        f"[{res['run_id']}] 客观总分={res['objective_score']}/80 "
        f"(A={res['A_score']}/{w.get('A_root_cause_and_ledger', 62)} [原始{res['A_raw_score']}], B={res['B_score']}, "
        f"C={res['C_score']}/{w.get('C_surgery_and_tests', 12)} [C1={res['C1_score']}, C2={res['C2_score']}], "
        f"T={res['T_score']}/{w.get('T_efficiency', 6)}, 耗时={res['timing']['elapsed_minutes']}m, 门禁轮次={res['rounds_completed']})"
    )
    if res["severe_flags"]:
        print("严重违规标记:", ", ".join(res["severe_flags"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
