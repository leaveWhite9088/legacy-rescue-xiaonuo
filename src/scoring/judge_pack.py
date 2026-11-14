#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成匿名盲评包 (leaderboard/blind/<pack_id>/) 与私有映射 (leaderboard/blind-maps/)。
注意：本脚本仅提取脱敏事实卡供独立评委盲评，不计算或落盘最终客观定稿分；
权威脚本打分与总分合成统一由评测发起人在最后运行 python leaderboard/finalize.py 完成。
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import re
import sys
import uuid

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))

from model_identity import canonical_model_id  # noqa: E402
from score_delivery import build_fact_card  # noqa: E402

RUNS_DIR = ROOT / "runs"
BLIND_DIR = ROOT / "leaderboard" / "blind"
BLIND_MAPS_DIR = ROOT / "leaderboard" / "blind-maps"


def _sanitize_report(text: str, tokens_to_redact: set[str]) -> str:
    out = text
    for tok in sorted(tokens_to_redact, key=len, reverse=True):
        if tok and len(tok) >= 3:
            out = re.sub(re.escape(tok), "匿名模型", out, flags=re.IGNORECASE)
    return out


def _render_fact_card_md(case_id: str, fact_data: dict, redact_tokens: set[str]) -> str:
    lines = [
        f"# 匿名事实卡 · {case_id}",
        "",
        "> 本事实卡已脱敏：不包含模型名称、客观得分与运行目录。请结合选手《事故排查与处置说明》与机器核验事实独立评判 D1/D2/D3。",
        "",
        "## 一、机器核验摘要（客观探针事实，不含分值）",
        "",
        "### 1. 暗病根因探针核验",
    ]
    bugs = fact_data["probe_summary"]["A1_bugs"]
    for bid, binfo in sorted(bugs.items()):
        checks = ", ".join(f"{c[0]}={'PASS' if c[1] else 'FAIL'}" for c in binfo["checks"])
        lines.append(f"- `{bid}`: {checks}")

    lines.append("")
    lines.append("### 2. 线上脏账与封账红线核验")
    for item in fact_data["probe_summary"]["A2_dirty_data"]:
        name, ok = item[0], item[1]
        lines.append(f"- `{name}`: {'PASS' if ok else 'FAIL'}")

    lines.append("")
    lines.append("### 3. 静音回归与伪反馈防误伤核验")
    for r in fact_data["probe_summary"]["B_regression"]:
        lines.append(f"- `{r['name']}`: {'PASS' if r['passed'] else 'FAIL'}")

    flags = fact_data["probe_summary"].get("severe_flags") or []
    if flags:
        lines.append(f"\n- **严重违规标记**：{', '.join(flags)}")

    diff = fact_data["code_changes"]
    lines.extend(
        [
            "",
            "### 4. 外科手术改动与突变测试统计",
            f"- 改动源码文件数：{diff['code_changed_files_count']}，有效变更行数：{diff['code_changed_lines']}",
        ]
    )
    for cf in diff["changed_files"]:
        lines.append(f"  - `{cf['file']}` (+{cf['added']} / -{cf['removed']})")

    mut = fact_data["mutation_tests"]
    if mut.get("tested_files"):
        for tf in mut["tested_files"]:
            lines.append(
                f"- 新增测试 `{tf['file']}`: 原件失败={tf['failed_on_buggy']}, 修复通过={tf['passed_on_fixed']}, 有效抓错={tf['valid_catch']}"
            )
    else:
        lines.append("- 新增测试：无")

    report_clean = _sanitize_report(fact_data.get("report_markdown", ""), redact_tokens)
    lines.extend(
        [
            "",
            "---",
            "## 二、选手提交的《事故排查与处置说明》原文",
            "",
            report_clean,
        ]
    )
    return "\n".join(lines)


def pack_blind_reviews(model_filter: str | None = None, run_dirs: list[Path] | None = None) -> dict:
    if run_dirs:
        targets = run_dirs
    else:
        targets = [p for p in sorted(RUNS_DIR.iterdir()) if p.is_dir() and (p / "protocol.json").exists()]
        if model_filter:
            cm = canonical_model_id(model_filter)
            filtered = []
            for p in targets:
                proto = json.loads((p / "protocol.json").read_text(encoding="utf-8"))
                if canonical_model_id(proto.get("model", "")) == cm:
                    filtered.append(p)
            targets = filtered

    if not targets:
        raise RuntimeError("没有找到可打包的 run 目录")

    pack_id = f"pack-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    pack_dir = BLIND_DIR / pack_id
    pack_dir.mkdir(parents=True, exist_ok=True)
    BLIND_MAPS_DIR.mkdir(parents=True, exist_ok=True)

    shuffled = list(targets)
    random.shuffle(shuffled)

    cases_manifest = []
    private_map = []
    model_names = set()

    for idx, rdir in enumerate(shuffled, start=1):
        proto = json.loads((rdir / "protocol.json").read_text(encoding="utf-8"))
        fact_data = build_fact_card(rdir)
        case_id = f"case-{idx:02d}"
        card_file = f"{case_id}.md"
        model_id = canonical_model_id(proto["model"])
        redact_set = {proto.get("model", ""), model_id, proto.get("run_id", ""), rdir.name}
        (pack_dir / card_file).write_text(_render_fact_card_md(case_id, fact_data, redact_set), encoding="utf-8")

        cases_manifest.append({"case_id": case_id, "fact_card": card_file})
        model_names.add(model_id)
        private_map.append(
            {
                "case_id": case_id,
                "run_id": proto["run_id"],
                "run_dir": str(rdir.resolve()),
                "model": proto["model"],
                "model_id": model_id,
            }
        )

    pack_manifest = {
        "benchmark": "legacy-rescue-xiaonuo",
        "pack_id": pack_id,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cases": cases_manifest,
    }
    (pack_dir / "pack.json").write_text(json.dumps(pack_manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    judge_readme = [
        f"# 匿名盲评指引 ({pack_id})",
        "",
        "你只能查看本目录内的 `case-XX.md` 匿名事实卡，严禁查看 `leaderboard/blind-maps/`、`leaderboard/reviews.jsonl` 或 `runs/`。",
        "",
        "## 评分维度（总分 20 分）",
        "- `D1` 根因归因准确度（0～8 分）：15 大跨层暗病（`BUG-01`～`BUG-15`，含启动猴子补丁、配置漂移、网关跨时区幂等、死信差额扣款、预览写副作用、缓存引用污染、金税 SDK 翻页与分位守恒、资源泄漏、调账反号等）定位是否精准、调用链是否与事实卡探针一致、有无编造。",
        "- `D2` 伪反馈、过期文档与规则边界定力（0～6 分）：是否准确识别 `F25`～`F38` 中的规则误解、2025 已废止旧 PRD 误导、销售施压篡改封账单、良性瞬态告警与架构诱导陷阱，严守权威《产品与账务规则 v2.6》。",
        "- `D3` 修复与数据订正方案的工程合理性（0～6 分）：改动是否最小外科手术精准（不乱删老租户兼容与历史孤岛）、是否严守 `2026-09`/`2026-10` 已封账红线（含 `INV-202610-0018` 原单不动与 `INV-202609-0012` 跨期调账）并分毫不差修平 `2026-11` 全部 11 处开放期脏账。",
        "",
        "## 提交命令（每个 case 提交一次）",
        "```sh",
        f"python src/scoring/judge_submit.py --pack-dir leaderboard/blind/{pack_id} --case-id case-01 \\",
        "  --judge-id <你的评委ID> --judge-model <你的模型或姓名> \\",
        "  --D1 <0-8> --D2 <0-6> --D3 <0-6> --evidence \"[引用的事实卡证据]\" --note \"<简短评语>\"",
        "```",
    ]
    (pack_dir / "JUDGE_README.md").write_text("\n".join(judge_readme) + "\n", encoding="utf-8")

    map_name = f"{'_'.join(sorted(model_names))}.{pack_id}.blind-map.json"
    map_path = BLIND_MAPS_DIR / map_name
    map_path.write_text(
        json.dumps(
            {
                "pack_id": pack_id,
                "model_id": sorted(model_names)[0] if len(model_names) == 1 else "multi",
                "mappings": private_map,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return {"pack_id": pack_id, "pack_dir": str(pack_dir), "map_file": str(map_path), "case_count": len(cases_manifest)}


def main() -> int:
    ap = argparse.ArgumentParser(description="生成匿名盲评包与私有映射")
    ap.add_argument("--model", default=None, help="只打包指定模型")
    ap.add_argument("--runs", nargs="*", default=None, help="显式指定 run 目录列表")
    args = ap.parse_args()

    run_dirs = [Path(r).resolve() for r in args.runs] if args.runs else None
    res = pack_blind_reviews(model_filter=args.model, run_dirs=run_dirs)
    print(f"盲评包生成成功：pack_id={res['pack_id']} (共 {res['case_count']} 份)")
    print(f"评委目录（仅交此目录）：{res['pack_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
