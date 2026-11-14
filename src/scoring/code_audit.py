#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""C 层评测：外科手术改动信噪比（5分） + 新增测试突变检验（5分）。"""
import difflib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATE_DIR = ROOT / "src" / "legacy_template"
CONFIG_PATH = ROOT / "configs" / "benchmark.json"

IGNORE_REL_PREFIXES = ("data/", "logs/", "__pycache__/", ".pytest_cache/", ".rescue_session")
IGNORE_EXACT = {"事故排查与处置说明.md", "data/yunce_billing.db"}


def _load_cfg() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _iter_source_files(base: Path) -> Dict[str, Path]:
    files = {}
    for p in sorted(base.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(base).as_posix()
        if rel in IGNORE_EXACT or any(rel.startswith(pref) for pref in IGNORE_REL_PREFIXES):
            continue
        if rel.endswith((".pyc", ".db", ".sqlite")):
            continue
        files[rel] = p
    return files


def compute_diff_stats(delivery_dir: Path) -> Dict[str, Any]:
    tmpl_files = _iter_source_files(TEMPLATE_DIR)
    deliv_files = _iter_source_files(delivery_dir)
    all_rels = sorted(set(tmpl_files.keys()) | set(deliv_files.keys()))

    changed_files: List[Dict[str, Any]] = []
    code_changed_lines = 0
    test_files_changed: List[str] = []

    for rel in all_rels:
        old_lines = (
            tmpl_files[rel].read_text(encoding="utf-8", errors="replace").splitlines()
            if rel in tmpl_files
            else []
        )
        new_lines = (
            deliv_files[rel].read_text(encoding="utf-8", errors="replace").splitlines()
            if rel in deliv_files
            else []
        )
        if old_lines == new_lines:
            continue

        diff = list(difflib.unified_diff(old_lines, new_lines, lineterm=""))
        added = sum(1 for ln in diff if ln.startswith("+") and not ln.startswith("+++") and ln[1:].strip())
        removed = sum(1 for ln in diff if ln.startswith("-") and not ln.startswith("---") and ln[1:].strip())
        effective = added + removed

        changed_files.append({"file": rel, "added": added, "removed": removed, "effective_lines": effective})
        if rel.startswith("tests/"):
            test_files_changed.append(rel)
        else:
            code_changed_lines += effective

    return {
        "changed_files": changed_files,
        "code_changed_files_count": len([x for x in changed_files if not x["file"].startswith("tests/")]),
        "code_changed_lines": code_changed_lines,
        "test_files_changed": test_files_changed,
    }


def score_c1_surgery(diff_stats: Dict[str, Any]) -> float:
    cfg = _load_cfg()["surgery"]
    lines = diff_stats["code_changed_lines"]
    if lines <= 0:
        return 0.0
    if lines < cfg["ideal_changed_lines_min"]:
        return round(5.0 * (lines / cfg["ideal_changed_lines_min"]), 3)
    if lines <= cfg["ideal_changed_lines_max"]:
        return 5.0
    if lines <= cfg["soft_limit_changed_lines"]:
        ratio = (lines - cfg["ideal_changed_lines_max"]) / (
            cfg["soft_limit_changed_lines"] - cfg["ideal_changed_lines_max"]
        )
        return round(5.0 - 2.5 * ratio, 3)
    if lines <= cfg["hard_limit_changed_lines"]:
        ratio = (lines - cfg["soft_limit_changed_lines"]) / (
            cfg["hard_limit_changed_lines"] - cfg["soft_limit_changed_lines"]
        )
        return round(max(0.0, 2.5 - 2.5 * ratio), 3)
    return 0.0


def run_mutation_tests(delivery_dir: Path, test_files_changed: List[str]) -> Dict[str, Any]:
    """C2: 把选手新增/修改的测试放到未修复原件上跑（必须红灯），再在交付件上跑（必须绿灯）。"""
    if not test_files_changed:
        return {"C2_score": 0.0, "tested_files": [], "note": "未新增或修改任何测试用例"}

    tmp_buggy = Path(tempfile.mkdtemp(prefix="mut_buggy_"))
    results = []
    try:
        shutil.copytree(
            TEMPLATE_DIR,
            tmp_buggy / "proj",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        buggy_proj = tmp_buggy / "proj"

        for rel in test_files_changed:
            src_test = delivery_dir / rel
            if not src_test.exists():
                continue
            dst_test = buggy_proj / rel
            dst_test.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_test, dst_test)

            # 1) 在未修复原件上运行
            p_buggy = subprocess.run(
                [sys.executable, "-m", "unittest", rel.replace("/", ".")[:-3]],
                cwd=str(buggy_proj),
                capture_output=True,
                text=True,
                timeout=30,
            )
            # 2) 在选手修复后的交付件上运行
            p_fixed = subprocess.run(
                [sys.executable, "-m", "unittest", rel.replace("/", ".")[:-3]],
                cwd=str(delivery_dir),
                capture_output=True,
                text=True,
                timeout=30,
            )
            failed_on_buggy = p_buggy.returncode != 0
            passed_on_fixed = p_fixed.returncode == 0
            results.append(
                {
                    "file": rel,
                    "failed_on_buggy": failed_on_buggy,
                    "passed_on_fixed": passed_on_fixed,
                    "valid_catch": failed_on_buggy and passed_on_fixed,
                }
            )
    finally:
        shutil.rmtree(tmp_buggy, ignore_errors=True)

    valid_cnt = sum(1 for r in results if r["valid_catch"])
    c2_score = 5.0 if valid_cnt >= 1 and all(r["passed_on_fixed"] for r in results) else (
        round(5.0 * valid_cnt / max(1, len(results)), 3)
    )
    return {"C2_score": c2_score, "tested_files": results}


def run_code_audit(delivery_dir: Path) -> Dict[str, Any]:
    diff_stats = compute_diff_stats(delivery_dir)
    c1 = score_c1_surgery(diff_stats)
    mut = run_mutation_tests(delivery_dir, diff_stats["test_files_changed"])
    return {
        "C_score": round(c1 + mut["C2_score"], 3),
        "C1_score": c1,
        "C2_score": mut["C2_score"],
        "diff_stats": diff_stats,
        "mutation_tests": mut,
    }


if __name__ == "__main__":
    target = Path(sys.argv[1]).resolve()
    print(json.dumps(run_code_audit(target), ensure_ascii=False, indent=2))
