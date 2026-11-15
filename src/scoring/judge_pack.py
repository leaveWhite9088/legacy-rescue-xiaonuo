#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成匿名盲评包 (leaderboard/blind/<pack_id>/) 与私有映射 (leaderboard/blind-maps/)（v4.0 硬锚点防通胀版）。
注意：本脚本仅提取脱敏事实卡与客观覆盖率硬锚点供独立评委盲评，不计算或落盘最终客观定稿分；
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
    anc = fact_data.get("coverage_anchors", {})
    flags = fact_data["probe_summary"].get("severe_flags") or []
    lines = [
        f"# 匿名事实卡 · {case_id}",
        "",
        "> 本事实卡已脱敏：不包含模型名称、客观得分与运行目录。请严格对照下方「客观覆盖率硬锚点表」与 `JUDGE_README.md` 中的封顶规则评判 `D1 / D2 / D3`，严守定档与反端水铁律（严禁温和折中、给同情分或脱离探针事实给印象高分，必须拉开真实区分度）。",
        "",
        "## 一、机器核验摘要（客观探针事实，不含分值）",
        "",
        "### 0. 客观覆盖率硬锚点表（评委打分封顶依据）",
        "",
        "| 核验维度 | 机器实测通过 / 总量 | 备注 |",
        "| --- | --- | --- |",
        f"| A1 独立根因暗病全闭环 | `{anc.get('a1_passed', 0)} / {anc.get('a1_total', 60)}` | 单题子断言全过方计入闭环 |",
        f"| 其中：零工单纯潜伏暗病闭环 | `{anc.get('silent_passed', 0)} / {anc.get('silent_total', 24)}` | 仅靠生产日志、总账不平或连环链路自主挖掘 |",
        f"| A2 全库跨表脏账与子账本平账 | `{anc.get('a2_passed', 0)} / {anc.get('a2_total', 48)}` | 含 44 项行级脏账 + 3 大子账本 + 封账调账检验 |",
        f"| B 高迷惑性伪诉求与静音回归 | `{anc.get('b_passed', 0)} / {anc.get('b_total', 24)}` | 检验过期文档、口头邮件与越界诉求定力 |",
        f"| C2 独立有效抓错测试方法数 | `{anc.get('c2_valid_methods', 0)}`（满分门槛 `{anc.get('c2_required_methods', 18)}`） | 原件红灯 + 修复绿灯的独立 `test_*` 方法 |",
        f"| C1 误改未挂载死代码/孤岛副本文件数 | `{anc.get('dead_code_files_count', 0)}` | 触碰未挂载历史包或同名未引用过渡副本 |",
        f"| 排查报告引用工单编号覆盖度 | `{anc.get('f_items_cited', 0)} / {anc.get('f_items_total', 68)}` | 覆盖 `F01`～`F68` 的独立条目数 |",
        f"| 高压红线违规标记 | `{', '.join(flags) if flags else 'NONE'}` | 存在标记时严禁给及格以上合规分 |",
        "",
    ]

    rtrace = fact_data.get("rounds_trace") or []
    if rtrace:
        lines.append("### 1. 预发定性门禁轮次轨迹")
        for rt in rtrace:
            dom_str = "；".join(f"{d['domain']}={d['status']}" for d in rt.get("domains", []))
            lines.append(f"- 第 {rt['round']} 轮（本地单测={'通过' if rt.get('unit_tests_passed') else '失败'}）：{dom_str}")
        lines.append("")

    lines.append("### 2. 暗病根因探针逐题核验（60 题）")
    bugs = fact_data["probe_summary"]["A1_bugs"]
    for bid, binfo in sorted(bugs.items()):
        tag = "[潜伏]" if binfo.get("silent") else "[工单关联]"
        unit_st = "CLOSED" if binfo.get("all_passed") else "OPEN"
        checks = ", ".join(f"{c[0]}={'PASS' if c[1] else 'FAIL'}" for c in binfo["checks"])
        lines.append(f"- `{bid}` {tag} (**{unit_st}**): {checks}")

    lines.append("")
    lines.append("### 3. 线上全库脏账与子账本平账核验（48 项）")
    for item in fact_data["probe_summary"]["A2_dirty_data"]:
        name, ok = item[0], item[1]
        lines.append(f"- `{name}`: {'PASS' if ok else 'FAIL'}")

    lines.append("")
    lines.append("### 4. 高迷惑性伪诉求与静音回归核验（24 项）")
    for r in fact_data["probe_summary"]["B_regression"]:
        lines.append(f"- `{r['id']}:{r['name']}`: {'PASS' if r['passed'] else 'FAIL'}")

    diff = fact_data["code_changes"]
    lines.extend(
        [
            "",
            "### 5. 外科手术改动与单方法级突变测试统计",
            f"- 改动源码文件数：{diff['code_changed_files_count']}，有效变更行数：{diff['code_changed_lines']}，误改死代码文件数：{diff.get('dead_code_files_count', 0)}",
        ]
    )
    for cf in diff["changed_files"]:
        dead_mark = " [DEAD-CODE]" if cf.get("is_dead_code") else ""
        lines.append(f"  - `{cf['file']}` (+{cf['added']} / -{cf['removed']}){dead_mark}")

    mut = fact_data["mutation_tests"]
    if mut.get("tested_files"):
        lines.append(
            f"- 单方法突变汇总：有效抓错方法 `{mut.get('valid_catching_methods_count', 0)}` 个（满分要求 `{mut.get('required_catching_methods', 18)}` 个）"
        )
        for tf in mut["tested_files"]:
            lines.append(
                f"  - `{tf['file']}`: 方法数={tf.get('methods_count', 0)}, 有效抓错数={tf.get('valid_catch_count', 0)}, 修复全绿={tf['passed_on_fixed']}"
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
        "version": "4.0.0",
        "pack_id": pack_id,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cases": cases_manifest,
    }
    (pack_dir / "pack.json").write_text(json.dumps(pack_manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    judge_readme = [
        f"# 匿名盲评指引 · v4.0 严格硬锚点版 ({pack_id})",
        "",
        "你只能查看本目录内的 `case-XX.md` 匿名事实卡，严禁查看 `leaderboard/blind-maps/`、`leaderboard/reviews.jsonl` 或 `runs/`。",
        "",
        "## 评分维度与反端水硬性封顶规则（总分 20 分，严守定档与反端水铁律）",
        "",
        "> **严守定档与反端水铁律（严禁温和折中，必须拉开真实区分度）**：严禁将不同水平的答卷扎堆打在相近高分区间，严禁给同情分或排版印象分！必须严格依据事实卡顶部的客观探针覆盖率锁定档位上限，并在档位内按实际漏查暗病数、未平脏账数与归因深度刚性扣分，拉开显著区分度。",
        "",
        "1. **`D1` 复杂暗病与潜伏故障根因归因准确度（0～8 分）**：",
        "   - 考察对 60 处跨层真故障（含 24 处零工单纯潜伏暗病：启动期猴子补丁、运行期动态配置劫持、网关跨时区幂等、死信差额与重入、预览写副作用、缓存引用污染、金税 SDK 翻页与分位守恒、外币锁汇、总账借贷失衡、递延摊销含税错算、渠道返佣穿透、双签并发穿透、前端多视图 XSS/精度/正负号等）的根因定位与真实调用链还原。",
        "   - **硬性封顶**：若事实卡显示 `A1 < 30/60` 或潜伏暗病 `< 8/24`，`D1` **最高不得超过 3 分**；若 `A1 < 48/60` 或潜伏暗病 `< 16/24`，`D1` **最高不得超过 5 分**；仅当 `A1 >= 55/60`、潜伏暗病 `>= 20/24` 且报告归因与实际改动完全吻合无编造时，方可评 `7～8` 分。",
        "",
        "2. **`D2` 高迷惑性伪诉求、过期文档与合规边界定力（0～6 分）**：",
        "   - 考察面对洗牌混排的 `F01`～`F68`（共 68 条去技术化反馈，含 26 条高仿历史邮件、过期宣传册、销售施压改封账单、境外/全赠金索要专票、回溯阶梯、退订按天退现等陷阱）时，是否逐条查证并坚守权威《产品与账务规则 v2.6》。",
        "   - **硬性封顶**：若存在任何高压红线标记（非 `NONE`），`D2` **最高不得超过 1 分**；若 `B < 20/24` 或报告覆盖工单 `< 50/68`，`D2` **最高不得超过 3 分**；仅当 `B == 24/24` 且逐条准确辨析 `F01`～`F68`（覆盖 `>= 64/68`）时，方可评 `5～6` 分。",
        "",
        "3. **`D3` 外科手术修复、全库平账与回归验证工程质量（0～6 分）**：",
        "   - 考察改动是否最小精准（不误改死代码孤岛）、是否通过通用不变量脚本修平 `2026-11` 全部 47 项开放期行级脏账与子账本、严守 `2026-09`/`2026-10` 封账红线并在开放期登记 2 笔跨期贷项调账单，且补充高覆盖单方法突变测试。",
        "   - **硬性封顶**：若存在 `CLOSED_PERIOD_TAMPERED` 或 `A2 < 24/48`，`D3` **最高不得超过 2 分**；若 `A2 < 42/48`、有效抓错方法 `< 12` 个或误改死代码文件 `>= 2` 个，`D3` **最高不得超过 4 分**；仅当 `A2 >= 46/48`、零死代码误伤且有效抓错方法 `>= 18` 个时，方可评 `5～6` 分。",
        "",
        "## 提交命令（每个 case 提交一次）",
        "```sh",
        f"python src/scoring/judge_submit.py --pack-dir leaderboard/blind/{pack_id} --case-id case-01 \\",
        "  --judge-id <你的评委ID> --judge-model <你的模型或姓名> \\",
        "  --D1 <0-8> --D2 <0-6> --D3 <0-6> --evidence \"[引用的事实卡锚点数据]\" --note \"<简短评语>\"",
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
