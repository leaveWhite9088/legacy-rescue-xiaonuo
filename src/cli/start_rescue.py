#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""官方开局脚本：向指定沙盒目录派发纯净事故现场，并打下不可伪造的起始时间锚点 t0。"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATE_DIR = ROOT / "src" / "legacy_template"
RUNS_DIR = ROOT / "runs"

sys.path.insert(0, str(ROOT / "src" / "scoring"))
from model_identity import canonical_model_id  # noqa: E402


def hash_tree(root_dir: Path) -> dict[str, str]:
    hashes = {}
    for p in sorted(root_dir.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root_dir).as_posix()
        if rel.startswith(".rescue_session") or "__pycache__" in rel or rel.endswith(".pyc"):
            continue
        h = hashlib.sha256(p.read_bytes()).hexdigest()
        hashes[rel] = h
    return hashes


def start_rescue(run_id: str, model: str, sandbox_dir: Path, overwrite: bool = False) -> dict:
    if sandbox_dir.exists():
        if not overwrite:
            raise FileExistsError(f"沙盒目录已存在: {sandbox_dir}（如需覆盖请加 --overwrite）")
        shutil.rmtree(sandbox_dir)

    shutil.copytree(
        TEMPLATE_DIR,
        sandbox_dir,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"),
    )

    t0_epoch = time.time()
    t0_iso = datetime.fromtimestamp(t0_epoch, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    initial_hashes = hash_tree(sandbox_dir)

    session_data = {
        "benchmark": "legacy-rescue-xiaonuo",
        "run_id": run_id,
        "model": model,
        "canonical_model": canonical_model_id(model),
        "sandbox_dir": str(sandbox_dir.resolve()),
        "t0_epoch": t0_epoch,
        "t0_iso": t0_iso,
        "initial_file_count": len(initial_hashes),
        "initial_hashes": initial_hashes,
    }

    (sandbox_dir / ".rescue_session.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "model": model,
                "t0_epoch": t0_epoch,
                "t0_iso": t0_iso,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "session_start.json").write_text(
        json.dumps(session_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return session_data


def _next_run_id(model: str) -> str:
    clean = canonical_model_id(model).replace(" ", "-")
    idx = 1
    while (RUNS_DIR / f"{clean}-r{idx}").exists() or (ROOT / "sandbox" / f"{clean}-r{idx}").exists():
        idx += 1
    return f"{clean}-r{idx}"


def main() -> int:
    ap = argparse.ArgumentParser(description="派发纯净事故现场并记录开局时间戳 t0")
    ap.add_argument("--model", required=True, help="被测模型真实名称（如 claude-sonnet-4-6、gpt-5 等）")
    ap.add_argument("--run-id", default=None, help="本次运行唯一 ID（省略时自动按 <model>-r1, r2 顺延分配）")
    ap.add_argument("--sandbox", default=None, help="选手工作沙盒路径（省略时自动设为 sandbox/<run_id>）")
    ap.add_argument("--overwrite", action="store_true", help="若沙盒目录已存在则清空重建")
    args = ap.parse_args()

    run_id = args.run_id or _next_run_id(args.model)
    sandbox_path = Path(args.sandbox) if args.sandbox else (ROOT / "sandbox" / run_id)

    data = start_rescue(run_id, args.model, sandbox_path, overwrite=args.overwrite)
    print(f"开局成功！run_id={data['run_id']}  model={data['model']}  t0={data['t0_iso']}")
    print(f"沙盒工作区：{data['sandbox_dir']}")
    print(f"收工命令：python src/cli/finish_rescue.py --sandbox sandbox/{data['run_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
