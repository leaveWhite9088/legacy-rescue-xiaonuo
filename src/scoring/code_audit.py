#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""C 层评测（v4.0 严格梯度版）：
- C1 外科手术改动信噪比（5.0 分）：理想有效变更行数 [260, 900]，软上限 1600，硬上限 2800；误改历史死代码归档目录每文件倒扣 1.0 分。
- C2 单方法级突变回归测试（5.0 分）：按 AST 提取新增或修改的独立 test_* 方法，分别在未修复原件与修复交付件上逐方法执行，需至少 18 个真实抓错方法（原件红灯 + 修复件绿灯）拿满 5.0 分。
"""
import ast
import difflib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATE_DIR = ROOT / "src" / "legacy_template"
CONFIG_PATH = ROOT / "configs" / "benchmark.json"

IGNORE_REL_PREFIXES = ("data/", "logs/", "__pycache__/", ".pytest_cache/", ".rescue_session")
IGNORE_EXACT = {"事故排查与处置说明.md", "data/yunce_billing.db"}

DEAD_CODE_PREFIXES = (
    "app/legacy_billing_2023_archive/",
    "app/legacy_cron_2024/",
    "app/legacy_ops_2024/",
    "app/legacy_erp_batch_2025/",
    "app/legacy_sdk_clients/",
    "app/adhoc_repair_scripts_2025/",
    "app/audit_compliance_archive/",
    "app/contract_clm_sync/",
    "app/cron_shadow_workers/",
    "app/customer_success_ops/",
    "app/enterprise_sso_and_rbac_legacy/",
    "app/internal_bi_cubes/",
    "app/migrations_legacy/",
    "app/payment_channels_legacy/",
    "app/silo_zhangwei_2024/",
    "app/silo_metering_pulse/",
    "app/silo_tax_jinsui/",
    "app/tariff_orchestrator_v2/",
    "app/tax_compliance_2025/",
    "app/usage_shards_2025/",
    "app/v1_5_transitional_2025/",
    "app/v3_pipeline/",
    "static/js_legacy_2024/",
)

DEAD_CODE_FILES = {
    "app/domain/tier_overage_calculator.py",
    "app/domain/gl_voucher_balancer.py",
    "app/domain/rebate_clawback_calc.py",
    "app/services/invoice_settlement_coordinator.py",
    "app/services/efapiao_redletter_sync.py",
    "app/services/subscription_proration_helper.py",
    "app/services/mrr_cohort_analyzer.py",
    "app/treasury/fx_revaluation_calculator.py",
    "app/treasury/wht_treaty_grossup.py",
    "app/gateway_ingest/usage_shard_aggregator.py",
    "app/reporting/vat_return_aggregator.py",
    "app/reporting/ifrs15_amortization_planner.py",
    "app/jobs/overdue_dunning_worker.py",
    "app/routes/export_download_helper.py",
    "static/js/views/billing_summary_card.js",
    "static/js/views/tax_split_calculator.js",
    "static/js/legacy_portal_v1.js",
    "static/js/table_renderer_old.js",
    "static/js/legacy_admin_2024_dead.js",
}


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
    dead_code_files_touched: List[str] = []

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
        is_dead = (rel in DEAD_CODE_FILES) or any(rel.startswith(dp) for dp in DEAD_CODE_PREFIXES)

        changed_files.append(
            {
                "file": rel,
                "added": added,
                "removed": removed,
                "effective_lines": effective,
                "is_dead_code": is_dead,
            }
        )
        if rel.startswith("tests/"):
            test_files_changed.append(rel)
        else:
            code_changed_lines += effective
            if is_dead:
                dead_code_files_touched.append(rel)

    return {
        "changed_files": changed_files,
        "code_changed_files_count": len([x for x in changed_files if not x["file"].startswith("tests/")]),
        "code_changed_lines": code_changed_lines,
        "dead_code_files_touched": dead_code_files_touched,
        "dead_code_files_count": len(dead_code_files_touched),
        "test_files_changed": test_files_changed,
    }


def score_c1_surgery(diff_stats: Dict[str, Any]) -> float:
    full_cfg = _load_cfg()
    cfg = full_cfg["surgery"]
    c1_max = float(full_cfg.get("weights", {}).get("C1_surgery_precision", 5.0))
    lines = int(diff_stats["code_changed_lines"])
    dead_cnt = int(diff_stats.get("dead_code_files_count", 0))
    dead_pen = float(cfg.get("dead_code_penalty_per_file", 1.0)) * dead_cnt

    if lines <= 0:
        return 0.0
    if lines < int(cfg["ideal_changed_lines_min"]):
        base = c1_max * (lines / float(cfg["ideal_changed_lines_min"]))
    elif lines <= int(cfg["ideal_changed_lines_max"]):
        base = c1_max
    elif lines <= int(cfg["soft_limit_changed_lines"]):
        ratio = (lines - cfg["ideal_changed_lines_max"]) / float(
            cfg["soft_limit_changed_lines"] - cfg["ideal_changed_lines_max"]
        )
        base = c1_max - (0.5 * c1_max) * ratio
    elif lines <= int(cfg["hard_limit_changed_lines"]):
        ratio = (lines - cfg["soft_limit_changed_lines"]) / float(
            cfg["hard_limit_changed_lines"] - cfg["soft_limit_changed_lines"]
        )
        base = max(0.0, (0.5 * c1_max) - (0.5 * c1_max) * ratio)
    else:
        base = 0.0

    return round(max(0.0, base - dead_pen), 3)


def _extract_test_methods(py_file: Path) -> Dict[Tuple[str, str], str]:
    """提取测试文件中的 {(类名或'', test_方法名): AST归一化源码}。"""
    if not py_file.exists():
        return {}
    try:
        tree = ast.parse(py_file.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return {}
    out: Dict[Tuple[str, str], str] = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub.name.startswith("test_"):
                    out[(node.name, sub.name)] = ast.dump(sub, include_attributes=False)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            out[("", node.name)] = ast.dump(node, include_attributes=False)
    return out


def _run_method_targets(project_dir: Path, targets: List[Dict[str, str]]) -> Dict[str, bool]:
    """在指定项目目录内逐方法执行 unittest 目标并返回 {target_id: passed_bool}。"""
    runner_code = """
import json, sys, unittest

targets = json.loads(sys.argv[1])
loader = unittest.TestLoader()
out = {}
for t in targets:
    tid = t["id"]
    dotted = t["dotted"]
    try:
        suite = loader.loadTestsFromName(dotted)
        res = unittest.TextTestRunner(stream=open("NUL" if sys.platform.startswith("win") else "/dev/null", "w")).run(suite)
        out[tid] = (res.testsRun > 0 and res.wasSuccessful())
    except Exception:
        out[tid] = False
print(json.dumps(out))
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(project_dir.resolve())
    proc = subprocess.run(
        [sys.executable, "-c", runner_code, json.dumps(targets)],
        cwd=str(project_dir.resolve()),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=90,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        return {t["id"]: False for t in targets}
    try:
        return json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception:
        return {t["id"]: False for t in targets}


def run_mutation_tests(delivery_dir: Path, test_files_changed: List[str]) -> Dict[str, Any]:
    """C2: 按新增/修改的独立 test_* 方法执行突变核验（未修复原件红灯 + 修复件绿灯）。"""
    cfg = _load_cfg().get("surgery", {})
    min_methods = int(cfg.get("min_catching_test_methods", 18))

    if not test_files_changed:
        return {
            "C2_score": 0.0,
            "required_catching_methods": min_methods,
            "valid_catching_methods_count": 0,
            "tested_methods": [],
            "tested_files": [],
            "note": "未新增或修改任何测试用例",
        }

    targets: List[Dict[str, str]] = []
    for rel in test_files_changed:
        if not rel.endswith(".py"):
            continue
        new_file = delivery_dir / rel
        if not new_file.exists():
            continue
        old_methods = _extract_test_methods(TEMPLATE_DIR / rel)
        new_methods = _extract_test_methods(new_file)
        mod_name = rel[:-3].replace("/", ".")
        for (cls_name, fn_name), ast_sig in sorted(new_methods.items()):
            if old_methods.get((cls_name, fn_name)) == ast_sig:
                continue
            dotted = f"{mod_name}.{cls_name}.{fn_name}" if cls_name else f"{mod_name}.{fn_name}"
            targets.append({"id": dotted, "file": rel, "dotted": dotted})

    if not targets:
        return {
            "C2_score": 0.0,
            "required_catching_methods": min_methods,
            "valid_catching_methods_count": 0,
            "tested_methods": [],
            "tested_files": [],
            "note": "未检测到新增或实质修改的 test_* 方法",
        }

    tmp_buggy = Path(tempfile.mkdtemp(prefix="mut_buggy_v4_"))
    try:
        shutil.copytree(
            TEMPLATE_DIR,
            tmp_buggy / "proj",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        buggy_proj = tmp_buggy / "proj"
        for rel in test_files_changed:
            src_test = delivery_dir / rel
            if src_test.exists():
                dst_test = buggy_proj / rel
                dst_test.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_test, dst_test)

        buggy_map = _run_method_targets(buggy_proj, targets)
        fixed_map = _run_method_targets(delivery_dir, targets)
    finally:
        shutil.rmtree(tmp_buggy, ignore_errors=True)

    method_results: List[Dict[str, Any]] = []
    by_file: Dict[str, List[Dict[str, Any]]] = {}
    for t in targets:
        tid = t["id"]
        passed_buggy = bool(buggy_map.get(tid, False))
        passed_fixed = bool(fixed_map.get(tid, False))
        failed_on_buggy = not passed_buggy
        valid_catch = failed_on_buggy and passed_fixed
        row = {
            "method": tid,
            "file": t["file"],
            "failed_on_buggy": failed_on_buggy,
            "passed_on_fixed": passed_fixed,
            "valid_catch": valid_catch,
        }
        method_results.append(row)
        by_file.setdefault(t["file"], []).append(row)

    file_summaries = []
    for f_rel, m_rows in sorted(by_file.items()):
        file_summaries.append(
            {
                "file": f_rel,
                "methods_count": len(m_rows),
                "valid_catch_count": sum(1 for x in m_rows if x["valid_catch"]),
                "failed_on_buggy": any(x["failed_on_buggy"] for x in m_rows),
                "passed_on_fixed": all(x["passed_on_fixed"] for x in m_rows),
                "valid_catch": any(x["valid_catch"] for x in m_rows) and all(x["passed_on_fixed"] for x in m_rows),
            }
        )

    c2_max = float(_load_cfg().get("weights", {}).get("C2_mutation_tests", 5.0))
    valid_cnt = sum(1 for r in method_results if r["valid_catch"])
    broken_fixed_cnt = sum(1 for r in method_results if not r["passed_on_fixed"])
    pass_ratio = (len(method_results) - broken_fixed_cnt) / float(max(1, len(method_results)))
    c2_score = round(c2_max * min(1.0, valid_cnt / float(max(1, min_methods))) * pass_ratio, 3)

    return {
        "C2_score": c2_score,
        "required_catching_methods": min_methods,
        "valid_catching_methods_count": valid_cnt,
        "broken_on_fixed_count": broken_fixed_cnt,
        "tested_methods": method_results,
        "tested_files": file_summaries,
    }


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
    target = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else TEMPLATE_DIR
    print(json.dumps(run_code_audit(target), ensure_ascii=False, indent=2))
