#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""评委提交盲评分：只追加到中心评审日志，不泄露其他评委分数。"""
import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import review_log  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="评委提交单条盲评分")
    ap.add_argument("--pack-dir", required=True, help="leaderboard/blind/<pack_id>/ 目录")
    ap.add_argument("--case-id", required=True, help="例如 case-01")
    ap.add_argument("--judge-id", required=True, help="评委唯一 ID")
    ap.add_argument("--judge-model", required=True, help="评委模型或姓名")
    ap.add_argument("--D1", type=float, required=True, help="根因归因准确度 (0-8)")
    ap.add_argument("--D2", type=float, required=True, help="伪反馈与规则边界定力 (0-6)")
    ap.add_argument("--D3", type=float, required=True, help="修复与数据订正方案工程合理性 (0-6)")
    ap.add_argument("--evidence", required=True, help="引用的事实卡证据编号或要点")
    ap.add_argument("--note", default="", help="评语/反证")
    ap.add_argument("--review-log", default=str(review_log.DEFAULT_LOG))
    a = ap.parse_args()

    pack_dir = Path(a.pack_dir).resolve()
    manifest_path = pack_dir / "pack.json"
    if not manifest_path.exists():
        print(f"找不到盲评包清单：{manifest_path}")
        return 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    pack_id = manifest["pack_id"]
    case_ids = [c["case_id"] for c in manifest.get("cases", [])]
    if a.case_id not in case_ids:
        print(f"无效 case_id={a.case_id}，可用: {', '.join(case_ids)}")
        return 1
    if not a.evidence.strip():
        print("--evidence 不能为空")
        return 1

    saved = review_log.append_review(
        a.review_log,
        {
            "judge_id": a.judge_id.strip(),
            "judge_model": a.judge_model.strip(),
            "pack_id": pack_id,
            "case_id": a.case_id,
            "D1": a.D1,
            "D2": a.D2,
            "D3": a.D3,
            "evidence": a.evidence.strip(),
            "note": a.note.strip(),
        },
        reject_duplicate=True,
    )
    print(f"提交成功！review_id={saved['review_id']}  pack_id={pack_id}  case_id={a.case_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
