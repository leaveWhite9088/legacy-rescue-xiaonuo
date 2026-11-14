#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""官方收工封包脚本：打下结束时间戳 t1、冻结交付快照并计算校验哈希。"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parent.parent.parent
RUNS_DIR = ROOT / "runs"


def hash_tree(root_dir: Path) -> dict[str, str]:
    hashes = {}
    for p in sorted(root_dir.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root_dir).as_posix()
        if rel.startswith(".rescue_session") or "__pycache__" in rel or rel.endswith(".pyc"):
            continue
        hashes[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return hashes


def finish_rescue(
    sandbox_dir: Path,
    run_id: str | None = None,
    tokens_input: int = 0,
    tokens_output: int = 0,
    commands_count: int = 0,
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

    start_data = json.loads(start_file.read_text(encoding="utf-8"))
    t0_epoch = float(start_data["t0_epoch"])
    t1_epoch = time.time()
    t1_iso = datetime.fromtimestamp(t1_epoch, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    elapsed_sec = max(0.0, t1_epoch - t0_epoch)

    delivery_dir = run_dir / "delivery"
    if delivery_dir.exists():
        shutil.rmtree(delivery_dir)
    shutil.copytree(
        sandbox_dir,
        delivery_dir,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", ".rescue_session.json"),
    )

    # 校验文件修改时间是否落在 [t0, t1] 窗口内
    init_hashes = start_data.get("initial_hashes", {})
    final_hashes = hash_tree(delivery_dir)
    mtime_anomalies = []
    for rel, fh in final_hashes.items():
        if init_hashes.get(rel) != fh:
            src_file = sandbox_dir / rel
            if src_file.exists():
                mt = src_file.stat().st_mtime
                if mt < t0_epoch - 5.0 or mt > t1_epoch + 5.0:
                    mtime_anomalies.append({"file": rel, "mtime": mt, "t0": t0_epoch, "t1": t1_epoch})

    bundle_digest = hashlib.sha256(
        json.dumps(final_hashes, sort_keys=True).encode("utf-8")
    ).hexdigest()

    protocol = {
        "benchmark": "legacy-rescue-xiaonuo",
        "run_id": run_id,
        "model": start_data["model"],
        "canonical_model": start_data["canonical_model"],
        "timing": {
            "t0_epoch": t0_epoch,
            "t0_iso": start_data["t0_iso"],
            "t1_epoch": t1_epoch,
            "t1_iso": t1_iso,
            "end_iso": t1_iso,
            "elapsed_seconds": round(elapsed_sec, 3),
            "elapsed_minutes": round(elapsed_sec / 60.0, 4),
            "mtime_anomalies": mtime_anomalies,
        },
        "diagnostics": {
            "tokens_input": tokens_input,
            "tokens_output": tokens_output,
            "commands_count": commands_count,
        },
        "integrity": {
            "delivery_sha256": bundle_digest,
            "file_count": len(final_hashes),
        },
    }
    (run_dir / "protocol.json").write_text(
        json.dumps(protocol, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return protocol


def main() -> int:
    ap = argparse.ArgumentParser(description="收工封包并记录结束时间戳 t1")
    ap.add_argument("--sandbox", required=True, help="选手工作沙盒目录路径")
    ap.add_argument("--run-id", default=None, help="运行 ID（默认从 .rescue_session.json 读取）")
    ap.add_argument("--tokens-input", type=int, default=0, help="累计输入词元消耗（诊断参考）")
    ap.add_argument("--tokens-output", type=int, default=0, help="累计输出词元消耗（诊断参考）")
    ap.add_argument("--commands-count", type=int, default=0, help="累计命令执行次数（诊断参考）")
    args = ap.parse_args()

    proto = finish_rescue(
        Path(args.sandbox),
        run_id=args.run_id,
        tokens_input=args.tokens_input,
        tokens_output=args.tokens_output,
        commands_count=args.commands_count,
    )
    print(f"收工封包完成！run_id={proto['run_id']}")
    print(f"端到端耗时：{proto['timing']['elapsed_minutes']:.2f} 分钟  交付哈希：{proto['integrity']['delivery_sha256'][:16]}...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
