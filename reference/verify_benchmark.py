#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""基准双基线、多轮检查点与两阶段评分闭环一键自检脚本（v3.0）：
1) 未修改原件基线：A1 = 1.5/25（仅 BUG-06 历史老租户兼容通过，其余 14 个暗病全红）、A2 = 0/10，且 B 层 16 项回归 100% 绿灯 (20/20)；
2) 选手多轮排障收尾与盲评阶段：start_rescue -> checkpoint_round(R1) -> apply_golden_patch -> checkpoint_round(R2) -> finish_rescue -> timing_audit -> judge_pack -> judge_submit，
   严格断言盲评阶段仅产出脱敏《事实卡数据.json》与盲评包，绝不提前生成《评分.json》；
3) 最终一键出榜阶段：运行 finalize 统一完成脚本客观分定稿（80/80）与盲评分合成（20/20），总分 100/100！
"""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src" / "cli"))
sys.path.insert(0, str(ROOT / "src" / "scoring"))
sys.path.insert(0, str(ROOT / "reference" / "golden_patch"))

from apply_golden_patch import apply_patch  # noqa: E402
from checkpoint_round import checkpoint_round  # noqa: E402
from eval_suite import run_eval  # noqa: E402
from finish_rescue import finish_rescue  # noqa: E402
from finalize import finalize_all  # noqa: E402
from judge_pack import pack_blind_reviews  # noqa: E402
from start_rescue import start_rescue  # noqa: E402
from timing_audit import audit_runs  # noqa: E402


def main() -> int:
    print("=== [1/4] 验证未修改原件基线 (15 暗病 / 12 脏账核验 / 16 静音回归) ===")
    raw_res = run_eval(ROOT / "src" / "legacy_template")
    print(f"未修改原件: A1={raw_res['A1_score']}/25, A2={raw_res['A2_score']}/10, B={raw_res['B_score']}/20")
    assert raw_res["A1_score"] == 1.5, f"未修改原件 A1 应严格为 1.5（仅 BUG-06 通过）: {raw_res}"
    assert raw_res["A2_score"] == 0.0, f"未修改原件 A2 应为 0: {raw_res}"
    assert raw_res["B_score"] == 20.0, f"未修改原件 B 层 16 项回归必须满分 20: {raw_res}"

    print("\n=== [2/4] 验证选手多轮检查点、收工封包与盲评打包阶段（不提前打分） ===")
    tmp_sandbox = Path(tempfile.mkdtemp(prefix="verify_golden_"))
    run_id = "GoldenBaseline-r1"
    pack_dir_created = None
    try:
        start_rescue(run_id, "GoldenBaseline", tmp_sandbox / "work", overwrite=True)
        cp1 = checkpoint_round(tmp_sandbox / "work", round_num=1, summary="Round 1 initial triage")
        assert cp1["round"] == 1
        apply_patch(tmp_sandbox / "work")
        cp2 = checkpoint_round(tmp_sandbox / "work", round_num=2, summary="Round 2 full surgical fix & DB audit")
        assert cp2["round"] == 2
        proto = finish_rescue(
            tmp_sandbox / "work",
            run_id=run_id,
            tokens_input=24000,
            tokens_output=6800,
            commands_count=22,
        )
        assert proto["diagnostics"]["rounds_completed"] == 2, f"多轮检查点记录异常: {proto}"

        run_dir = ROOT / "runs" / run_id
        ta = audit_runs(ROOT / "runs")
        assert ta["ok"], f"计时审计失败: {ta}"

        pack_res = pack_blind_reviews(run_dirs=[run_dir])
        pack_dir_created = Path(pack_res["pack_dir"])
        assert (run_dir / "事实卡数据.json").exists(), "盲评打包后应生成脱敏事实卡数据"
        assert not (run_dir / "评分.json").exists(), "盲评打包阶段严禁提前生成 评分.json"

        print("\n=== [3/4] 验证独立评委盲评阶段（仅提交 D 分，仍未出客观定稿分） ===")
        sub_cmd = [
            sys.executable,
            str(ROOT / "src" / "scoring" / "judge_submit.py"),
            "--pack-dir", str(pack_dir_created),
            "--case-id", "case-01",
            "--judge-id", "self-check-judge",
            "--judge-model", "self-check",
            "--D1", "8", "--D2", "6", "--D3", "6",
            "--evidence", "[BUG-01..15 PASS] [11_dirty_data_fixed] [CLOSED_period_preserved]",
            "--note", "v3.0 黄金补丁自检满分",
            "--review-log", str(tmp_sandbox / "test_reviews.jsonl"),
        ]
        rc = subprocess.run(sub_cmd, check=False).returncode
        assert rc == 0, "judge_submit.py 执行失败"
        assert not (run_dir / "评分.json").exists(), "评委盲评阶段仍不应生成 评分.json"

        print("\n=== [4/4] 验证最终一键出榜阶段（统一执行脚本打分定稿 + 总分合成） ===")
        verdicts = finalize_all(
            model_filter="GoldenBaseline",
            review_log_path=tmp_sandbox / "test_reviews.jsonl",
            dry_run=True,
        )
        assert len(verdicts) == 1, f"未找到汇总结果: {verdicts}"
        v = verdicts[0]
        r = v["runs"][0]
        print(
            f"最终定稿明细: A={r['A']}/35 (A1={r['A1']}, A2={r['A2']}), "
            f"B={r['B']}/20, C={r['C']}/10 (C1={r['C1']}, C2={r['C2']}), "
            f"T={r['T']}/15, D={r['D']}/20 => 总分={v['mean_total']}/100"
        )
        assert r["A"] == 35.0, f"黄金补丁 A 未满分: {r}"
        assert r["B"] == 20.0, f"黄金补丁 B 未满分: {r}"
        assert r["C"] == 10.0, f"黄金补丁 C 未满分: {r}"
        assert r["T"] == 15.0, f"黄金补丁 T 未满分: {r}"
        assert r["D"] == 20.0, f"黄金补丁 D 未满分: {r}"
        assert v["mean_total"] == 100.0, f"黄金补丁全链路总分未达 100: {v}"
        print("v3.0 黄金补丁多轮与两阶段闭环自检 100% 通过！")
    finally:
        shutil.rmtree(tmp_sandbox, ignore_errors=True)
        shutil.rmtree(ROOT / "runs" / run_id, ignore_errors=True)
        if pack_dir_created and pack_dir_created.exists():
            shutil.rmtree(pack_dir_created, ignore_errors=True)
        for p in (ROOT / "leaderboard" / "blind-maps").glob("GoldenBaseline.*"):
            p.unlink(missing_ok=True)
        for p in (ROOT / "leaderboard" / "blind-maps").glob("*.blind-map.json"):
            if "GoldenBaseline" in p.read_text(encoding="utf-8", errors="ignore"):
                p.unlink(missing_ok=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
