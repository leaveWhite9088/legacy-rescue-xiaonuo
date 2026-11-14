#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""多轮排障阶段留痕脚本（可选）：
支持多轮（如三轮递进深挖）测试模式下，在每轮排障结束时记录当前耗时、变更文件清单与本地单测状态至
runs/<run_id>/rounds/round-XX.json，不会触发正式封包，也不会泄露或调用任何主控评分探针。
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent.parent
RUNS_DIR = ROOT / "runs"


def _hash_tree(root_dir: Path) -> dict[str, str]:
    hashes = {}
    for p in sorted(root_dir.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root_dir).as_posix()
        if rel.startswith(".rescue_session") or "__pycache__" in rel or rel.endswith(".pyc"):
            continue
        hashes[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return hashes


def checkpoint_round(
    sandbox_dir: Path,
    round_num: int,
    run_id: str | None = None,
    summary: str = "",
) -> dict:
    if round_num < 1:
        raise ValueError("round 轮次编号必须 >= 1")

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

    start_data = json.loads(start_file.read_text(encoding="utf-8"))
    t0_epoch = float(start_data["t0_epoch"])
    now_epoch = time.time()
    now_iso = datetime.fromtimestamp(now_epoch, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    elapsed_sec = max(0.0, now_epoch - t0_epoch)

    init_hashes = start_data.get("initial_hashes", {})
    curr_hashes = _hash_tree(sandbox_dir)
    changed_files = sorted(
        rel for rel, ch in curr_hashes.items() if init_hashes.get(rel) != ch
    )

    ut_proc = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        cwd=str(sandbox_dir),
        capture_output=True,
        text=True,
        timeout=45,
    )

    rounds_dir = run_dir / "rounds"
    rounds_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "run_id": run_id,
        "round": int(round_num),
        "checkpoint_iso": now_iso,
        "elapsed_seconds": round(elapsed_sec, 3),
        "elapsed_minutes": round(elapsed_sec / 60.0, 4),
        "changed_files_count": len(changed_files),
        "changed_files": changed_files,
        "unit_tests_passed": ut_proc.returncode == 0,
        "summary": summary.strip(),
    }
    out_file = rounds_dir / f"round-{int(round_num):02d}.json"
    out_file.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def main() -> int:
    ap = argparse.ArgumentParser(description="记录多轮排障的阶段性轮次快照（不封包、不提前计分）")
    ap.add_argument("--sandbox", required=True, help="选手工作沙盒目录路径")
    ap.add_argument("--round", type=int, required=True, help="当前轮次编号（如 1, 2, 3）")
    ap.add_argument("--run-id", default=None, help="运行 ID（默认从 .rescue_session.json 读取）")
    ap.add_argument("--summary", default="", help="本轮排查进展摘要（可选）")
    args = ap.parse_args()

    rec = checkpoint_round(Path(args.sandbox).resolve(), round_num=args.round, run_id=args.run_id, summary=args.summary)
    print(
        f"[Round {rec['round']}] 已记录阶段快照：run_id={rec['run_id']}, "
        f"累计耗时={rec['elapsed_minutes']:.2f} 分钟, 累计变更文件={rec['changed_files_count']} 个, "
        f"本地单测={'PASS' if rec['unit_tests_passed'] else 'FAIL'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
