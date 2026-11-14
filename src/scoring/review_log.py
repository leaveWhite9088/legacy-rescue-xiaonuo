# -*- coding: utf-8 -*-
"""追加式中心评审日志 (leaderboard/reviews.jsonl) 读写与校验。"""
from datetime import datetime, timezone
import json
from pathlib import Path
import uuid

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_LOG = ROOT / "leaderboard" / "reviews.jsonl"
SCHEMA_VERSION = "1.0"


class ReviewLogError(Exception):
    pass


class DuplicateReviewError(ReviewLogError):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_reviews(log_path: str | Path = DEFAULT_LOG) -> list[dict]:
    p = Path(log_path)
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def append_review(log_path: str | Path, rec: dict, reject_duplicate: bool = True) -> dict:
    p = Path(log_path)
    p.parent.mkdir(parents=True, exist_ok=True)

    d1 = float(rec["D1"])
    d2 = float(rec["D2"])
    d3 = float(rec["D3"])
    if not (0.0 <= d1 <= 8.0 and 0.0 <= d2 <= 6.0 and 0.0 <= d3 <= 6.0):
        raise ReviewLogError("评分超界：要求 D1∈[0,8], D2∈[0,6], D3∈[0,6]")

    if reject_duplicate:
        existing = read_reviews(p)
        for ex in existing:
            if (
                ex.get("pack_id") == rec.get("pack_id")
                and ex.get("case_id") == rec.get("case_id")
                and ex.get("judge_id") == rec.get("judge_id")
            ):
                raise DuplicateReviewError(
                    f"评委 {rec['judge_id']} 已对 {rec['pack_id']}/{rec['case_id']} 提交过评分"
                )

    saved = {
        "schema_version": SCHEMA_VERSION,
        "review_id": f"rev_{uuid.uuid4().hex[:10]}",
        "submitted_at": _now_iso(),
        "judge_id": rec["judge_id"],
        "judge_model": rec["judge_model"],
        "pack_id": rec["pack_id"],
        "case_id": rec["case_id"],
        "D1": round(d1, 2),
        "D2": round(d2, 2),
        "D3": round(d3, 2),
        "D_total": round(d1 + d2 + d3, 2),
        "evidence": rec["evidence"],
        "note": rec.get("note", ""),
    }
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(saved, ensure_ascii=False) + "\n")
    return saved
