#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""聚合中心评审日志中的 D 层盲评分。"""
import argparse
import json
from pathlib import Path
import statistics
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
import review_log  # noqa: E402


def merge_reviews(log_path: str | Path = review_log.DEFAULT_LOG, aggregate: str = "mean") -> dict:
    rows = review_log.read_reviews(log_path)
    grouped: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        key = (r["pack_id"], r["case_id"])
        grouped.setdefault(key, []).append(r)

    merged = {}
    agg_fn = statistics.mean if aggregate == "mean" else statistics.median
    for (pack_id, case_id), items in sorted(grouped.items()):
        d1 = round(agg_fn([x["D1"] for x in items]), 3)
        d2 = round(agg_fn([x["D2"] for x in items]), 3)
        d3 = round(agg_fn([x["D3"] for x in items]), 3)
        merged[f"{pack_id}/{case_id}"] = {
            "pack_id": pack_id,
            "case_id": case_id,
            "judge_count": len(items),
            "D1": d1,
            "D2": d2,
            "D3": d3,
            "D_total": round(d1 + d2 + d3, 3),
        }
    return {"aggregate": aggregate, "cases": merged}


def main() -> int:
    ap = argparse.ArgumentParser(description="汇总中心评审日志")
    ap.add_argument("--log", default=str(review_log.DEFAULT_LOG))
    ap.add_argument("--out", default=str(ROOT / "leaderboard" / "reviews.merged.json"))
    ap.add_argument("--aggregate", choices=("mean", "median"), default="mean")
    args = ap.parse_args()

    res = merge_reviews(args.log, aggregate=args.aggregate)
    Path(args.out).write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已聚合 {len(res['cases'])} 个盲评 case -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
