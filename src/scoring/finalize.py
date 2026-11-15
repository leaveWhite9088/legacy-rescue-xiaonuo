#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一键出榜最终定稿：
在所有评委盲评完成后由评测发起人手动运行。
本脚本对每个参评 run 的冻结交付物重新执行官方客观评分（A/B/C/T 权威定稿）与计时审计，
再与中心评审日志（reviews.jsonl）中的盲评 D 分统一合成为 100 分制总分，输出裁决留档与总榜。
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))

from model_identity import canonical_model_id  # noqa: E402
from review_merge import merge_reviews  # noqa: E402
import review_log  # noqa: E402
from score_delivery import score_run  # noqa: E402
from timing_audit import audit_runs  # noqa: E402

LEADERBOARD_MD = ROOT / "leaderboard" / "scores.md"
VERDICTS_DIR = ROOT / "leaderboard" / "verdicts"
BLIND_MAPS_DIR = ROOT / "leaderboard" / "blind-maps"


def _discover_models_and_runs() -> dict[str, list[dict]]:
    by_model: dict[str, list[dict]] = {}
    seen_runs: dict[str, set[str]] = {}
    if not BLIND_MAPS_DIR.exists():
        return by_model
    for mf in sorted(BLIND_MAPS_DIR.glob("*.blind-map.json")):
        bm = json.loads(mf.read_text(encoding="utf-8"))
        pack_id = bm["pack_id"]
        for item in bm.get("mappings", []):
            mid = canonical_model_id(item.get("model_id") or item.get("model", ""))
            rid = item["run_id"]
            if rid in seen_runs.setdefault(mid, set()):
                continue
            seen_runs[mid].add(rid)
            by_model.setdefault(mid, []).append(
                {
                    "pack_id": pack_id,
                    "case_id": item["case_id"],
                    "run_id": rid,
                    "run_dir": Path(item["run_dir"]),
                }
            )
    return by_model


def finalize_all(
    model_filter: str | None = None,
    review_log_path: str | Path = review_log.DEFAULT_LOG,
    d_aggregate: str = "mean",
    min_judges: int = 1,
    allow_partial: bool = False,
    dry_run: bool = False,
) -> list[dict]:
    by_model = _discover_models_and_runs()
    if not by_model:
        raise RuntimeError("leaderboard/blind-maps/ 下未发现盲评映射")

    if model_filter:
        cm = canonical_model_id(model_filter)
        if cm not in by_model:
            raise RuntimeError(f"未找到模型 {cm} 的盲评映射")
        target_models = [cm]
    else:
        target_models = sorted(by_model.keys())

    merged_d = merge_reviews(review_log_path, aggregate=d_aggregate)["cases"]
    timing_rep = audit_runs(ROOT / "runs")
    overlap_runs = {r["run_id"] for r in timing_rep["runs"] if r["overlaps"] or r["mtime_anomalies"]}

    verdicts = []
    for mid in target_models:
        entries = by_model[mid]
        run_summaries = []
        for ent in entries:
            rdir = ent["run_dir"]
            d_key = f"{ent['pack_id']}/{ent['case_id']}"
            d_info = merged_d.get(d_key)
            if not d_info or d_info["judge_count"] < min_judges:
                if allow_partial:
                    continue
                raise RuntimeError(f"case {d_key} ({ent['run_id']}) 尚未满足 min_judges={min_judges}")

            if not (rdir / "protocol.json").exists() or not (rdir / "delivery").exists():
                if allow_partial:
                    continue
                raise FileNotFoundError(f"run 缺少冻结交付目录或协议文件: {rdir}")

            # 关键：在最终出榜时重新执行官方客观脚本打分定稿，绝不信任选手阶段遗留的任何分数文件
            obj = score_run(rdir, record=not dry_run)

            total = round(obj["objective_score"] + d_info["D_total"], 3)
            rt_list = obj["timing"].get("round_timings", [])
            rt_brief = " / ".join(f"R{x['round']}:{x['round_duration_minutes']:.1f}m" for x in rt_list) if rt_list else "-"
            run_summaries.append(
                {
                    "run_id": ent["run_id"],
                    "pack_id": ent["pack_id"],
                    "case_id": ent["case_id"],
                    "A": obj["A_score"],
                    "A_raw": obj.get("A_raw_score", obj["A_score"]),
                    "A1": obj["A1_score"],
                    "A2": obj["A2_score"],
                    "B": obj["B_score"],
                    "C": obj["C_score"],
                    "C1": obj["C1_score"],
                    "C2": obj["C2_score"],
                    "T": obj["T_score"],
                    "objective_score": obj["objective_score"],
                    "D": d_info["D_total"],
                    "D1": d_info["D1"],
                    "D2": d_info["D2"],
                    "D3": d_info["D3"],
                    "penalty_factor": obj["penalty_factor"],
                    "severe_flags": obj["severe_flags"],
                    "total": total,
                    "rounds_completed": obj.get("rounds_completed", len(rt_list)),
                    "round_timings_brief": rt_brief,
                    "elapsed_minutes": obj["timing"]["elapsed_minutes"],
                    "timing_valid": ent["run_id"] not in overlap_runs,
                    "judge_count": d_info["judge_count"],
                }
            )

        if not run_summaries:
            continue

        mean_total = round(statistics.mean(r["total"] for r in run_summaries), 2)
        verdict = {
            "model_id": mid,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "runs_count": len(run_summaries),
            "mean_total": mean_total,
            "mean_A": round(statistics.mean(r["A"] for r in run_summaries), 2),
            "mean_B": round(statistics.mean(r["B"] for r in run_summaries), 2),
            "mean_C": round(statistics.mean(r["C"] for r in run_summaries), 2),
            "mean_T": round(statistics.mean(r["T"] for r in run_summaries), 2),
            "mean_D": round(statistics.mean(r["D"] for r in run_summaries), 2),
            "mean_elapsed_min": round(statistics.mean(r["elapsed_minutes"] for r in run_summaries), 2),
            "all_timing_valid": all(r["timing_valid"] for r in run_summaries),
            "runs": run_summaries,
        }
        verdicts.append(verdict)
        if not dry_run:
            VERDICTS_DIR.mkdir(parents=True, exist_ok=True)
            (VERDICTS_DIR / f"{mid}.json").write_text(
                json.dumps(verdict, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    verdicts.sort(key=lambda x: x["mean_total"], reverse=True)
    if not dry_run:
        lines = [
            "# 《遗留救火 · 复杂暗病排障基准》排行榜",
            "",
            f"> 更新时间：{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')}  ｜  评分制：A(62, 二次方梯度) + B(扣分闸门) + C(12) + T(6) + D(20) = 100",
            "",
            "## 总榜（按模型总分均值排名）",
            "",
            "| 排名 | 模型 | 总分均值(100) | A 根因与脏账(62) | B 回归扣分(0起) | C 手术与测试(12) | T 效率(6) | D 盲评(20) | 平均耗时(m) | 局数 | 计时审计 |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
        for idx, v in enumerate(verdicts, start=1):
            t_flag = "通过" if v["all_timing_valid"] else "异常"
            lines.append(
                f"| {idx} | {v['model_id']} | **{v['mean_total']:.2f}** | {v['mean_A']:.2f} | {v['mean_B']:.2f} | "
                f"{v['mean_C']:.2f} | {v['mean_T']:.2f} | {v['mean_D']:.2f} | {v['mean_elapsed_min']:.2f} | {v['runs_count']} | {t_flag} |"
            )

        for v in verdicts:
            lines.extend(
                [
                    "",
                    f"### 最终成绩明细 · {v['model_id']}",
                    "",
                    "| Run ID | 总分(100) | A1(45) | A2(17) | B(0) | C1(6) | C2(6) | T(6) | D1(8) | D2(6) | D3(6) | 门禁轮次 | 分段耗时 | 总耗时(m) | 惩罚系数 |",
                    "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: |",
                ]
            )
            for r in v["runs"]:
                lines.append(
                    f"| {r['run_id']} | **{r['total']:.2f}** | {r['A1']:.2f} | {r['A2']:.2f} | {r['B']:.2f} | "
                    f"{r['C1']:.2f} | {r['C2']:.2f} | {r['T']:.2f} | {r['D1']:.2f} | {r['D2']:.2f} | {r['D3']:.2f} | "
                    f"{r['rounds_completed']} | {r['round_timings_brief']} | {r['elapsed_minutes']:.2f} | {r['penalty_factor']} |"
                )

        LEADERBOARD_MD.parent.mkdir(parents=True, exist_ok=True)
        LEADERBOARD_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return verdicts


def main() -> int:
    ap = argparse.ArgumentParser(description="一键重算权威客观分、合并盲评 D 分并生成排行榜")
    ap.add_argument("--model", default=None)
    ap.add_argument("--review-log", default=str(review_log.DEFAULT_LOG))
    ap.add_argument("--d-aggregate", choices=("mean", "median"), default="mean")
    ap.add_argument("--min-judges", type=int, default=1)
    ap.add_argument("--allow-partial", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    verdicts = finalize_all(
        model_filter=args.model,
        review_log_path=args.review_log,
        d_aggregate=args.d_aggregate,
        min_judges=args.min_judges,
        allow_partial=args.allow_partial,
        dry_run=args.dry_run,
    )
    for v in verdicts:
        print(
            f"{v['model_id']}: 总分={v['mean_total']:.2f} "
            f"(A={v['mean_A']}, B={v['mean_B']}, C={v['mean_C']}, T={v['mean_T']}, D={v['mean_D']})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
