# -*- coding: utf-8 -*-
"""幂等记录表过期键归档清理算子（保留最近 7 天防重窗口）。"""
import sqlite3
from typing import Dict


def purge_expired_idempotency_keys(conn: sqlite3.Connection, cutoff_iso: str, dry_run: bool = True) -> Dict[str, int]:
    cnt = conn.execute(
        "SELECT COUNT(*) AS c FROM idempotency_records WHERE created_at < ?",
        (cutoff_iso,),
    ).fetchone()["c"]
    if not dry_run and cnt > 0:
        conn.execute("DELETE FROM idempotency_records WHERE created_at < ?", (cutoff_iso,))
    return {"expired_candidates": int(cnt), "deleted": 0 if dry_run else int(cnt)}
