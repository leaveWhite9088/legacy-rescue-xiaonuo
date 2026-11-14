# -*- coding: utf-8 -*-
"""线下银行公户回单导入、企业户名模糊匹配与自动入账认领服务。"""
from datetime import datetime, timezone
import sqlite3
import uuid
from typing import Any, Dict, List

from app.domain.ledger import topup_cash
from app.utils.csv_parser import bigram_jaccard_similarity, parse_delimited_records


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def import_and_match_bank_csv(conn: sqlite3.Connection, csv_text: str, auto_claim_bps: int = 8500) -> Dict[str, Any]:
    """解析银行对公水单 CSV（列：serial_no,payer_name,amount_cents,tx_date），按企业名称相似度匹配租户。"""
    records = parse_delimited_records(csv_text, delimiter=",")
    tenants = conn.execute("SELECT id, company_name FROM tenants WHERE status IN ('ACTIVE', 'ACTIVE_LEGACY')").fetchall()
    now = _now_iso()

    imported = 0
    auto_claimed = 0
    results: List[Dict[str, Any]] = []

    for rec in records:
        serial = rec.get("serial_no", "").strip()
        payer = rec.get("payer_name", "").strip()
        tx_date = rec.get("tx_date", now[:10]).strip()
        try:
            amt = int(rec.get("amount_cents", "0"))
        except ValueError:
            continue
        if not serial or amt <= 0:
            continue

        dup = conn.execute("SELECT id FROM bank_statement_imports WHERE bank_serial_no = ?", (serial,)).fetchone()
        if dup:
            continue

        best_tid = None
        best_score = 0.0
        for t in tenants:
            sim = bigram_jaccard_similarity(payer, t["company_name"])
            if sim > best_score:
                best_score = sim
                best_tid = t["id"]

        conf_bps = int(round(best_score * 10000))
        status = "MATCHED_PENDING" if conf_bps >= 5000 else "UNMATCHED"
        imp_id = f"bsi_{uuid.uuid4().hex[:10]}"

        if best_tid and conf_bps >= auto_claim_bps:
            topup_cash(conn, best_tid, amt, ref_id=serial, note=f"银企直连自动认领:{serial}")
            status = "AUTO_CLAIMED"
            auto_claimed += 1

        conn.execute(
            """
            INSERT INTO bank_statement_imports (
                id, bank_serial_no, payer_company_name, amount_cents, tx_date,
                matched_tenant_id, match_confidence_bps, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (imp_id, serial, payer, amt, tx_date, best_tid, conf_bps, status, now),
        )
        imported += 1
        results.append({
            "import_id": imp_id,
            "bank_serial_no": serial,
            "matched_tenant_id": best_tid,
            "confidence_bps": conf_bps,
            "status": status,
        })

    return {"imported_count": imported, "auto_claimed_count": auto_claimed, "items": results}
