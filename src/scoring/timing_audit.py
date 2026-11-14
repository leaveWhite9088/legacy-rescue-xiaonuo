#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""时间真实性审计：校验窗口完整性、文件 mtime 异常与同模型多局时间重叠。"""
import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from model_identity import canonical_model_id  # noqa: E402


def audit_runs(runs_dir: Path) -> dict:
    if not runs_dir.exists():
        return {"ok": False, "runs": [], "overlap_count": 0, "mtime_anomaly_count": 0}

    dirs = [runs_dir] if (runs_dir / "protocol.json").exists() else [
        p for p in sorted(runs_dir.iterdir()) if p.is_dir() and (p / "protocol.json").exists()
    ]
    rows = []
    for d in dirs:
        proto = json.loads((d / "protocol.json").read_text(encoding="utf-8"))
        t = proto.get("timing", {})
        t0 = t.get("t0_epoch")
        t1 = t.get("t1_epoch")
        if t0 is None or t1 is None or t1 < t0:
            continue
        rows.append(
            {
                "run_id": proto.get("run_id", d.name),
                "model": canonical_model_id(proto.get("model", d.name)),
                "t0": float(t0),
                "t1": float(t1),
                "elapsed_min": float(t.get("elapsed_minutes", (t1 - t0) / 60.0)),
                "mtime_anomalies": t.get("mtime_anomalies", []),
                "overlaps": [],
            }
        )

    for a in rows:
        for b in rows:
            if a is b or a["model"] != b["model"]:
                continue
            if max(a["t0"], b["t0"]) < min(a["t1"], b["t1"]):
                a["overlaps"].append(b["run_id"])

    overlap_cnt = sum(1 for r in rows if r["overlaps"])
    mtime_cnt = sum(1 for r in rows if r["mtime_anomalies"])
    return {
        "ok": overlap_cnt == 0 and mtime_cnt == 0,
        "overlap_count": overlap_cnt,
        "mtime_anomaly_count": mtime_cnt,
        "runs": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="审计端到端计时窗口与同模型重叠")
    ap.add_argument("runs_dir", nargs="?", default="runs", help="runs 目录路径")
    ap.add_argument("--strict", action="store_true", help="发现异常时退出码为 1")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    rep = audit_runs(Path(args.runs_dir).resolve())
    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        for r in rep["runs"]:
            ov = ", ".join(r["overlaps"]) if r["overlaps"] else "-"
            mt = len(r["mtime_anomalies"])
            print(f"{r['run_id']:28} model={r['model']:16} {r['elapsed_min']:6.2f}m  mtime_err={mt}  overlap={ov}")
        print(f"审计结果：ok={rep['ok']} (overlap={rep['overlap_count']}, mtime_err={rep['mtime_anomaly_count']})")

    if args.strict and not rep["ok"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
