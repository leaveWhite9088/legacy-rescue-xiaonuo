#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""三轮递进排障提交与预发定性门禁脚本（最多 3 轮）：
每轮排障结束提交时：
1) 记录本轮单轮耗时与自起局以来的累计耗时；
2) 在 runs/<run_id>/rounds/round-0X/snapshot/ 冻结不可篡改的阶段交付快照（供最终 finalize 计算轮次折扣）；
3) 返回七大业务域的去分母定性灯号（「已闭环」或「仍有异常未闭环」），严格隐藏题目数量、伪反馈陷阱与封账红线状态，且绝不提前计算或写入正式得分。
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent.parent
RUNS_DIR = ROOT / "runs"
MAX_ROUNDS = 3

sys.path.insert(0, str(ROOT / "src" / "scoring"))
from gatekeeper import run_qualitative_gatekeeper  # noqa: E402


def hash_tree(root_dir: Path) -> dict[str, str]:
    hashes = {}
    for p in sorted(root_dir.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root_dir).as_posix()
        if rel.startswith(".rescue_session") or "__pycache__" in rel or rel.endswith(".pyc") or ".pytest_cache" in rel:
            continue
        hashes[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return hashes


def checkpoint_round(
    sandbox_dir: Path,
    round_num: int | None = None,
    run_id: str | None = None,
    summary: str = "",
) -> dict:
    meta_file = sandbox_dir / ".rescue_session.json"
    if not run_id:
        if not meta_file.exists():
            raise FileNotFoundError(f"找不到 {meta_file}，请显式传入 --run-id")
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        run_id = meta["run_id"]

    run_dir = RUNS_DIR / run_id
    start_file = run_dir / "session_start.json"
    if not start_file.exists():
        raise FileNotFoundError(f"主控侧找不到开局记录: {start_file}")
    if (run_dir / "protocol.json").exists():
        raise RuntimeError(f"该运行局 {run_id} 已执行 finish_rescue 正式封包，不可再提交轮次门禁")

    rounds_dir = run_dir / "rounds"
    rounds_dir.mkdir(parents=True, exist_ok=True)
    existing_files = sorted(rounds_dir.glob("round-*.json"))
    next_round = len(existing_files) + 1

    if next_round > MAX_ROUNDS:
        raise RuntimeError(f"已用满最多 {MAX_ROUNDS} 轮预发门禁巡检配额，请直接执行 finish_rescue.py 正式收工封包")

    if round_num is not None and int(round_num) != next_round:
        raise ValueError(
            f"轮次编号必须严格递增且不可覆写历史轮次：已完成 {len(existing_files)} 轮，本次应提交 --round {next_round}"
        )
    actual_round = next_round

    start_data = json.loads(start_file.read_text(encoding="utf-8"))
    t0_epoch = float(start_data["t0_epoch"])
    prev_epoch = t0_epoch
    if existing_files:
        last_rec = json.loads(existing_files[-1].read_text(encoding="utf-8"))
        prev_epoch = float(last_rec.get("checkpoint_epoch", t0_epoch))

    now_epoch = time.time()
    now_iso = datetime.fromtimestamp(now_epoch, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    elapsed_sec = max(0.0, now_epoch - t0_epoch)
    round_dur_sec = max(0.0, now_epoch - prev_epoch)

    # 先冻结不可变阶段快照，再运行定性门禁，彻底阻断“看回执后偷改同轮快照”的可能
    snap_parent = rounds_dir / f"round-{actual_round:02d}"
    snap_dir = snap_parent / "snapshot"
    if snap_dir.exists():
        shutil.rmtree(snap_dir)
    snap_parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        sandbox_dir,
        snap_dir,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", ".rescue_session.json"),
    )

    init_hashes = start_data.get("initial_hashes", {})
    curr_hashes = hash_tree(snap_dir)
    snapshot_sha256 = hashlib.sha256(
        json.dumps(curr_hashes, sort_keys=True).encode("utf-8")
    ).hexdigest()
    changed_files = sorted(rel for rel, ch in curr_hashes.items() if init_hashes.get(rel) != ch)

    ut_proc = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        cwd=str(snap_dir),
        capture_output=True,
        text=True,
        timeout=45,
    )

    gatekeeper_res = run_qualitative_gatekeeper(snap_dir)

    record = {
        "run_id": run_id,
        "round": actual_round,
        "checkpoint_epoch": now_epoch,
        "checkpoint_iso": now_iso,
        "round_duration_seconds": round(round_dur_sec, 3),
        "round_duration_minutes": round(round_dur_sec / 60.0, 4),
        "elapsed_seconds": round(elapsed_sec, 3),
        "elapsed_minutes": round(elapsed_sec / 60.0, 4),
        "snapshot_sha256": snapshot_sha256,
        "changed_files_count": len(changed_files),
        "changed_files": changed_files,
        "unit_tests_passed": ut_proc.returncode == 0,
        "gatekeeper": gatekeeper_res,
        "summary": summary.strip(),
    }
    out_file = rounds_dir / f"round-{actual_round:02d}.json"
    out_file.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def main() -> int:
    ap = argparse.ArgumentParser(description="提交单轮排障成果并获取七大业务域定性门禁回执（最多 3 轮）")
    ap.add_argument("--sandbox", required=True, help="选手工作沙盒目录路径")
    ap.add_argument("--round", type=int, default=None, help="当前轮次编号（1 / 2 / 3，须严格递增，可省略自动顺延）")
    ap.add_argument("--run-id", default=None, help="运行 ID（默认从 .rescue_session.json 读取）")
    ap.add_argument("--summary", default="", help="本轮排查进展摘要（可选）")
    args = ap.parse_args()

    rec = checkpoint_round(
        Path(args.sandbox).resolve(),
        round_num=args.round,
        run_id=args.run_id,
        summary=args.summary,
    )
    print(f"=== 预发门禁定性巡检回执 · 第 {rec['round']} / {MAX_ROUNDS} 轮 ({rec['run_id']}) ===")
    print(
        f"耗时统计：本轮耗时 {rec['round_duration_minutes']:.2f} 分钟 ｜ "
        f"累计耗时 {rec['elapsed_minutes']:.2f} 分钟 ｜ "
        f"沙盒本地单测：{'通过' if rec['unit_tests_passed'] else '存在失败'}"
    )
    print("业务域巡检状态（仅示定性灯号，不含分母与题目明细）：")
    for d in rec["gatekeeper"]["domains"]:
        print(f"  - {d['domain']}：{d['status']}")

    if rec["gatekeeper"]["all_closed"]:
        print(
            "门禁结论：七大业务域均已闭环！（注：历史封账红线、存量老客户兼容与伪反馈合规边界不在门禁提示范围内，"
            "请自行最终核验报告与测试无误后，执行 finish_rescue.py 收工封包，无需再跑后续轮次。）"
        )
    elif rec["round"] < MAX_ROUNDS:
        print(
            f"门禁结论：仍有未闭环业务域。请针对「仍有异常未闭环」的方向继续深入排查隐蔽链路与开放期脏账"
            f"（切勿提前运行 finish_rescue.py），修复完成后提交第 {rec['round'] + 1} 轮门禁巡检。"
        )
    else:
        print(
            f"门禁结论：已用满全部 {MAX_ROUNDS} 轮门禁巡检配额。请完成最终修复与排查说明整理后，执行 finish_rescue.py 收工封包。"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
