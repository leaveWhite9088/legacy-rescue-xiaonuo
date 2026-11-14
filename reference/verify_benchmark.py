#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""基准双基线、三轮定性门禁微折（1.0 / 0.9 / 0.8）与两阶段盲评定稿闭环自检脚本：
1) 未修改原件基线：A1 = 1.5/25（仅 BUG-06 通过）、A2 = 0/10，B 层 16 项回归 100% 绿灯 (20/20)；
2) 三轮去分母定性门禁、防重刷/防超轮锁与 1.0/0.9/0.8 阶梯折扣精度核验（且验证历史封账篡改陷阱绝不在门禁回执中泄密）；
3) 首轮一次封神黄金路径：start_rescue -> apply_golden_patch -> checkpoint_round(R1全闭环) -> finish_rescue -> timing_audit -> judge_pack -> judge_submit，断言盲评阶段绝不提前生成《评分.json》；
4) 最终一键出榜阶段：运行 finalize 统一完成脚本客观分定稿（80/80）与盲评分合成（20/20），总分 100/100！
"""
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src" / "cli"))
sys.path.insert(0, str(ROOT / "src" / "scoring"))
sys.path.insert(0, str(ROOT / "reference" / "golden_patch"))

from apply_golden_patch import _replace_once, apply_patch  # noqa: E402
from checkpoint_round import checkpoint_round  # noqa: E402
from eval_suite import run_eval  # noqa: E402
from finish_rescue import finish_rescue  # noqa: E402
from finalize import finalize_all  # noqa: E402
from gatekeeper import run_qualitative_gatekeeper  # noqa: E402
from judge_pack import pack_blind_reviews  # noqa: E402
from score_delivery import score_run  # noqa: E402
from start_rescue import start_rescue  # noqa: E402
from timing_audit import audit_runs  # noqa: E402


def main() -> int:
    print("=== [1/5] 验证未修改原件基线 (15 暗病 / 12 脏账核验 / 16 静音回归) ===")
    raw_res = run_eval(ROOT / "src" / "legacy_template")
    print(f"未修改原件: A1={raw_res['A1_score']}/25, A2={raw_res['A2_score']}/10, B={raw_res['B_score']}/20")
    assert raw_res["A1_score"] == 1.5, f"未修改原件 A1 应严格为 1.5（仅 BUG-06 通过）: {raw_res}"
    assert raw_res["A2_score"] == 0.0, f"未修改原件 A2 应为 0: {raw_res}"
    assert raw_res["B_score"] == 20.0, f"未修改原件 B 层 16 项回归必须满分 20: {raw_res}"

    print("\n=== [2/5] 验证三轮去分母定性门禁、陷阱静默防泄密与 1.0/0.9/0.8 阶梯折扣计分 ===")
    tmp_mr = Path(tempfile.mkdtemp(prefix="verify_mr_"))
    mr_run_id = "MultiRoundProbe-r1"
    try:
        work_mr = tmp_mr / "work"
        start_rescue(mr_run_id, "MultiRoundProbe", work_mr, overwrite=True)

        # 第 1 轮：未修复直接提交门禁 -> 五大业务域全部「仍有异常未闭环」
        r1 = checkpoint_round(work_mr, round_num=1, summary="R1 baseline probe")
        assert r1["round"] == 1 and not r1["gatekeeper"]["all_closed"]
        assert all(not d["closed"] for d in r1["gatekeeper"]["domains"])

        # 防作弊校验：禁止重复传 --round 1 覆写首轮快照
        dup_blocked = False
        try:
            checkpoint_round(work_mr, round_num=1)
        except ValueError:
            dup_blocked = True
        assert dup_blocked, "重复覆写第 1 轮快照未被拦截！"

        # 第 2 轮：仅修复 BUG-08 (2.0分) -> 应在第 2 轮拿到 0.9 折扣 (1.8分)
        _replace_once(
            work_mr / "app" / "hotfixes" / "hotfix_20261031_tz_and_vip.py",
            'def apply_oct31_high_value_vat_patch() -> None:\n'
            '    global _PATCH_INSTALLED\n'
            '    if _PATCH_INSTALLED:\n'
            '        return\n'
            '    pricing_mod.compute_tax_breakdown = _hotfix_tax_wrapper\n'
            '    _PATCH_INSTALLED = True',
            'def apply_oct31_high_value_vat_patch() -> None:\n'
            '    return',
        )
        r2 = checkpoint_round(work_mr, round_num=2, summary="R2 hotfix removed")
        assert r2["round"] == 2 and not r2["gatekeeper"]["all_closed"]

        # 第 3 轮：重置干净工作树并打上全量黄金补丁 -> 其余新修项应按第 3 轮 0.8 折扣计分
        meta_bytes = (work_mr / ".rescue_session.json").read_bytes()
        shutil.rmtree(work_mr)
        shutil.copytree(ROOT / "src" / "legacy_template", work_mr)
        (work_mr / ".rescue_session.json").write_bytes(meta_bytes)
        apply_patch(work_mr)
        r3 = checkpoint_round(work_mr, round_num=3, summary="R3 full fix")
        assert r3["round"] == 3 and r3["gatekeeper"]["all_closed"]

        # 防超轮校验：第 4 次调用门禁必须报错拦截
        over_blocked = False
        try:
            checkpoint_round(work_mr)
        except RuntimeError:
            over_blocked = True
        assert over_blocked, "超过 3 轮门禁配额未被拦截！"

        # 陷阱静默校验：若篡改已封账 INV-202610-0018，定性门禁绝不报警提示（留待最终 finalize 严惩）
        trap_copy = tmp_mr / "trap_check"
        shutil.copytree(work_mr, trap_copy)
        c_trap = sqlite3.connect(str(trap_copy / "data" / "yunce_billing.db"))
        c_trap.execute("UPDATE invoices SET total_cents = 39900 WHERE id = 'INV-202610-0018'")
        c_trap.commit()
        c_trap.close()
        gk_trap = run_qualitative_gatekeeper(trap_copy)
        assert gk_trap["all_closed"], "门禁回执泄露了历史封账篡改陷阱状态！"

        finish_rescue(work_mr, run_id=mr_run_id)
        mr_score = score_run(ROOT / "runs" / mr_run_id, record=False)
        # 核算期望值：BUG-06(1.5*1.0=1.5) + BUG-08(2.0*0.9=1.8) + 其余A1(21.5*0.8=17.2) = 20.5；A2(10.0*0.8=8.0) => A = 28.5
        print(
            f"三轮阶梯折扣核验: A_raw={mr_score['A_raw_score']}/35 -> 折后 A={mr_score['A_score']}/35 "
            f"(A1={mr_score['A1_score']}, A2={mr_score['A2_score']})"
        )
        assert mr_score["A_raw_score"] == 35.0
        assert mr_score["A1_score"] == 20.5, f"A1 轮次折扣计算不符预期 20.5: {mr_score['A1_score']}"
        assert mr_score["A2_score"] == 8.0, f"A2 轮次折扣计算不符预期 8.0: {mr_score['A2_score']}"
        assert mr_score["A_score"] == 28.5
    finally:
        shutil.rmtree(tmp_mr, ignore_errors=True)
        shutil.rmtree(ROOT / "runs" / mr_run_id, ignore_errors=True)

    print("\n=== [3/5] 验证首轮一次闭环黄金路径与盲评打包阶段（不提前打分） ===")
    tmp_sandbox = Path(tempfile.mkdtemp(prefix="verify_golden_"))
    run_id = "GoldenBaseline-r1"
    pack_dir_created = None
    try:
        start_rescue(run_id, "GoldenBaseline", tmp_sandbox / "work", overwrite=True)
        apply_patch(tmp_sandbox / "work")
        cp1 = checkpoint_round(tmp_sandbox / "work", round_num=1, summary="Round 1 complete surgical fix")
        assert cp1["round"] == 1 and cp1["gatekeeper"]["all_closed"], f"黄金补丁首轮门禁应全绿闭环: {cp1}"

        proto = finish_rescue(
            tmp_sandbox / "work",
            run_id=run_id,
            tokens_input=24000,
            tokens_output=6800,
            commands_count=22,
        )
        assert proto["diagnostics"]["rounds_completed"] == 1
        assert len(proto["timing"]["round_timings"]) == 1

        run_dir = ROOT / "runs" / run_id
        ta = audit_runs(ROOT / "runs")
        assert ta["ok"], f"计时审计失败: {ta}"

        pack_res = pack_blind_reviews(run_dirs=[run_dir])
        pack_dir_created = Path(pack_res["pack_dir"])
        assert (run_dir / "事实卡数据.json").exists(), "盲评打包后应生成脱敏事实卡数据"
        assert not (run_dir / "评分.json").exists(), "盲评打包阶段严禁提前生成 评分.json"

        print("\n=== [4/5] 验证独立评委盲评阶段（仅提交 D 分，仍未出客观定稿分） ===")
        sub_cmd = [
            sys.executable,
            str(ROOT / "src" / "scoring" / "judge_submit.py"),
            "--pack-dir", str(pack_dir_created),
            "--case-id", "case-01",
            "--judge-id", "self-check-judge",
            "--judge-model", "self-check",
            "--D1", "8", "--D2", "6", "--D3", "6",
            "--evidence", "[BUG-01..15 R1 PASS] [11_dirty_data_fixed] [CLOSED_period_preserved]",
            "--note", "首轮一次闭环黄金补丁满分",
            "--review-log", str(tmp_sandbox / "test_reviews.jsonl"),
        ]
        rc = subprocess.run(sub_cmd, check=False).returncode
        assert rc == 0, "judge_submit.py 执行失败"
        assert not (run_dir / "评分.json").exists(), "评委盲评阶段仍不应生成 评分.json"

        print("\n=== [5/5] 验证最终一键出榜阶段（统一执行脚本打分定稿 + 总分合成） ===")
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
            f"T={r['T']}/15 (总耗时={r['elapsed_minutes']}m, 分段={r['round_timings_brief']}), "
            f"D={r['D']}/20 => 总分={v['mean_total']}/100"
        )
        assert r["A"] == 35.0, f"黄金补丁 A 未满分: {r}"
        assert r["B"] == 20.0, f"黄金补丁 B 未满分: {r}"
        assert r["C"] == 10.0, f"黄金补丁 C 未满分: {r}"
        assert r["T"] == 15.0, f"黄金补丁 T 未满分: {r}"
        assert r["D"] == 20.0, f"黄金补丁 D 未满分: {r}"
        assert v["mean_total"] == 100.0, f"黄金补丁全链路总分未达 100: {v}"
        print("三轮定性门禁、分段计时与两阶段闭环自检 100% 通过！")
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
