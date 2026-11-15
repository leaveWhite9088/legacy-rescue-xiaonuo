#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v4.0 基准全链路端到端校准与自检脚本（验证零分基线、满分黄金补丁、三轮阶梯折扣、T曲线区分度与盲评打包）。"""
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src" / "scoring"))
sys.path.insert(0, str(ROOT / "reference" / "golden_patch"))

from apply_golden_patch import apply_golden_patch  # noqa: E402
from code_audit import compute_diff_stats, score_c1_surgery  # noqa: E402
from eval_suite import run_eval  # noqa: E402
from score_delivery import compute_t_score, score_run  # noqa: E402


def _run_cli(args: list[str]) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        [sys.executable, *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"CLI failed ({args}):\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")
    return proc


def _cleanup_verify_artifacts(run_ids: list[str], pack_ids: list[str]) -> None:
    for rid in run_ids:
        shutil.rmtree(ROOT / "sandbox" / rid, ignore_errors=True)
        shutil.rmtree(ROOT / "runs" / rid, ignore_errors=True)
    for pid in pack_ids:
        shutil.rmtree(ROOT / "leaderboard" / "blind" / pid, ignore_errors=True)
        bmap_dir = ROOT / "leaderboard" / "blind-maps"
        if bmap_dir.exists():
            for mf in bmap_dir.glob(f"*{pid}*"):
                mf.unlink(missing_ok=True)


def main() -> None:
    created_runs: list[str] = []
    created_packs: list[str] = []

    try:
        cfg = json.loads((ROOT / "configs" / "benchmark.json").read_text(encoding="utf-8"))
        w = cfg["weights"]
        a_max = float(w["A_root_cause_and_ledger"])
        a1_max = float(w["A1_bugs"])
        a2_max = float(w["A2_dirty_data"])
        b_max = float(cfg["regression"]["max_score"])
        c1_max = float(w["C1_surgery_precision"])

        print("=== [1/5] 校验未修复模板零分基线 (Unpatched Template Baseline) ===")
        base_ev = run_eval(ROOT / "src" / "legacy_template")
        failed_b_base = [c["id"] for c in base_ev["B"]["checks"] if not c["passed"]]
        print(
            f"  Unpatched -> A1={base_ev['A1']['score']}/{a1_max}, A2={base_ev['A2']['score']}/{a2_max}, "
            f"B={base_ev['B']['score']}/{b_max} (failed_b={failed_b_base}), severe={base_ev['severe_flags']}"
        )
        assert base_ev["A1"]["score"] == 0.0, f"Expected A1=0.0 on template, got {base_ev['A1']['score']}"
        assert base_ev["A2"]["score"] == 0.0, f"Expected A2=0.0 on template, got {base_ev['A2']['score']}"
        assert base_ev["B"]["score"] == b_max and not failed_b_base, f"Expected B={b_max} on template, got {base_ev['B']['score']}: {failed_b_base}"
        assert base_ev["severe_flags"] == [], f"Unexpected severe flags on template: {base_ev['severe_flags']}"

        print("\n=== [2/5] 校验耗时效率 T 曲线区分度 (13.51m vs 60.0m) ===")
        t_fast = compute_t_score(13.51, a_max, b_max, cfg)
        t_slow = compute_t_score(60.0, a_max, b_max, cfg)
        t_gap = round(t_fast["T_score"] - t_slow["T_score"], 3)
        print(f"  T(13.51m)={t_fast['T_score']} vs T(60.0m)={t_slow['T_score']} -> Gap={t_gap} pts")
        assert t_gap >= 2.5, f"Expected T gap >= 2.5 pts, got {t_gap}"

        print("\n=== [3/5] 校验一轮全闭环黄金补丁满分与盲评包生成 (Golden 80.0/80.0) ===")
        rid_gold = "VerifyV4Gold-r1"
        _cleanup_verify_artifacts([rid_gold], [])
        created_runs.append(rid_gold)

        _run_cli(["src/cli/start_rescue.py", "--model", "VerifyV4Gold"])
        sb_gold = ROOT / "sandbox" / rid_gold
        apply_golden_patch(sb_gold)

        diff_stats = compute_diff_stats(sb_gold)
        c1_val = score_c1_surgery(diff_stats)
        print(
            f"  Diff stats -> files={diff_stats['code_changed_files_count']}, "
            f"effective_lines={diff_stats['code_changed_lines']}, dead_touched={diff_stats['dead_code_files_count']}, C1={c1_val}"
        )

        ev_gold = run_eval(sb_gold)
        failed_a1 = [k for k, v in ev_gold["A1"]["bugs"].items() if not v["all_passed"]]
        failed_a2 = [c["id"] for c in ev_gold["A2"]["checks"] if not c["passed"]]
        failed_b = [c["id"] for c in ev_gold["B"]["checks"] if not c["passed"]]
        print(
            f"  Eval -> A1={ev_gold['A1']['score']}/{a1_max} (failed={failed_a1}), "
            f"A2={ev_gold['A2']['score']}/{a2_max} (failed={failed_a2}), "
            f"B={ev_gold['B']['score']}/{b_max} (failed={failed_b}), severe={ev_gold['severe_flags']}"
        )
        assert abs(ev_gold["A1"]["score"] - a1_max) <= 0.01 and not failed_a1, f"Golden A1 failed bugs: {failed_a1}"
        assert abs(ev_gold["A2"]["score"] - a2_max) <= 0.01 and not failed_a2, f"Golden A2 failed checks: {failed_a2}"
        assert ev_gold["B"]["score"] == b_max and not failed_b, f"Golden B failed checks: {failed_b}"
        assert ev_gold["severe_flags"] == [], f"Golden triggered severe flags: {ev_gold['severe_flags']}"
        assert c1_val == c1_max, f"Expected C1={c1_max}, got {c1_val} (lines={diff_stats['code_changed_lines']})"

        cp1 = _run_cli(["src/cli/checkpoint_round.py", "--sandbox", str(sb_gold), "--round", "1", "--summary", "首轮全量修复与平账"])
        assert "七大业务域均已闭环" in cp1.stdout, f"Expected Round 1 all closed in gatekeeper:\n{cp1.stdout}"
        assert "沙盒本地单测：通过" in cp1.stdout, f"Expected sandbox local unit tests all green:\n{cp1.stdout}"

        _run_cli([
            "src/cli/finish_rescue.py",
            "--sandbox", str(sb_gold),
            "--tokens-input", "120000",
            "--tokens-output", "18000",
            "--commands-count", "24",
        ])

        score_res = score_run(ROOT / "runs" / rid_gold, record=False)
        c2_info = score_res["details"]["mutation_tests"]
        failed_mut = [m for m in c2_info.get("tested_methods", []) if not m["valid_catch"]]
        print(
            f"  ScoreRun -> Objective={score_res['objective_score']}/80.0 "
            f"(A={score_res['A_score']}, B={score_res['B_score']}, "
            f"C={score_res['C_score']} [C1={score_res['C1_score']}, C2={score_res['C2_score']}, valid_methods={c2_info.get('valid_catching_methods_count')}, non_catch={len(failed_mut)}], "
            f"T={score_res['T_score']})"
        )
        assert score_res["objective_score"] == 80.0, f"Expected 80.0/80.0, got {score_res['objective_score']} (non_catch={failed_mut})"

        score_json = ROOT / "runs" / rid_gold / "评分.json"
        assert not score_json.exists(), "score_run(record=False) must not write 评分.json!"

        _run_cli(["src/scoring/timing_audit.py", f"runs/{rid_gold}", "--strict"])
        jp_out = _run_cli(["src/scoring/judge_pack.py", "--runs", f"runs/{rid_gold}"])
        import re
        m_pid = re.search(r"pack_id=([^\s(]+)", jp_out.stdout)
        assert m_pid, f"Could not parse pack_id from judge_pack output:\n{jp_out.stdout}"
        pack_id = m_pid.group(1)
        created_packs.append(pack_id)
        case_md = (ROOT / "leaderboard" / "blind" / pack_id / "case-01.md").read_text(encoding="utf-8")
        assert "客观覆盖率硬锚点表" in case_md, "Missing Objective Coverage Fact Table in blind case card!"
        assert not score_json.exists(), "judge_pack.py must not write 评分.json prematurely!"

        print("\n=== [4/5] 校验三轮渐进门禁反馈与 1.00 / 0.85 / 0.70 轮次阶梯系数 ===")
        rid_prog = "VerifyV4Multi-r1"
        _cleanup_verify_artifacts([rid_prog], [])
        created_runs.append(rid_prog)

        _run_cli(["src/cli/start_rescue.py", "--model", "VerifyV4Multi"])
        sb_prog = ROOT / "sandbox" / rid_prog

        # 第 1 轮仅修 D1, D2（不修数据库）
        apply_golden_patch(sb_prog, domains=["D1", "D2"], with_db_repair=False, with_tests_and_report=False)
        r1_out = _run_cli(["src/cli/checkpoint_round.py", "--sandbox", str(sb_prog), "--round", "1", "--summary", "完成计量与钱包修复"])
        assert "仍有异常未闭环" in r1_out.stdout, "Round 1 partial patch must report open domains!"

        # 第 2 轮补修 D3, D4, D5
        apply_golden_patch(sb_prog, domains=["D3", "D4", "D5"], with_db_repair=False, with_tests_and_report=False)
        r2_out = _run_cli(["src/cli/checkpoint_round.py", "--sandbox", str(sb_prog), "--round", "2", "--summary", "完成跨境、发票与总账修复"])
        assert "仍有异常未闭环" in r2_out.stdout, "Round 2 partial patch must still report D6/D7 open!"

        # 第 3 轮补齐 D6, D7 + 全库平账 + 测试报告
        apply_golden_patch(sb_prog, domains=["D6", "D7"], with_db_repair=True, with_tests_and_report=True)
        r3_out = _run_cli(["src/cli/checkpoint_round.py", "--sandbox", str(sb_prog), "--round", "3", "--summary", "完成渠道催收安全与全库平账"])
        assert "七大业务域均已闭环" in r3_out.stdout, f"Round 3 full patch should close all 7 domains:\n{r3_out.stdout}"

        _run_cli(["src/cli/finish_rescue.py", "--sandbox", str(sb_prog), "--tokens-input", "1", "--tokens-output", "1", "--commands-count", "10"])
        multi_score = score_run(ROOT / "runs" / rid_prog, record=False)
        a_multi = multi_score["A_score"]
        print(f"  3-Round Discounted A Score -> {a_multi}/{a_max} (Raw={multi_score['A_raw_score']}, strictly discounted by 1.00/0.85/0.70 + convex!)")
        assert 0.50 * a_max < a_multi < 0.92 * a_max, f"Expected discounted A in ({0.50 * a_max}, {0.92 * a_max}), got {a_multi}"

        print("\n=== [5/5] 全部校准断言 100% 通过！清理临时校验产物 ===")
    finally:
        _cleanup_verify_artifacts(created_runs, created_packs)


if __name__ == "__main__":
    main()
