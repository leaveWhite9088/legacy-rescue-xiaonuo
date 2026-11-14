# -*- coding: utf-8 -*-
"""财务封账哈希链（WORM - Write Once Read Many）防篡改链式签名计算与核验工具。"""
import hashlib
import json
from typing import Any, Dict, List


def compute_period_seal_chain(closed_periods: List[Dict[str, Any]], genesis_seed: str = "YUNCE_FIN_GENESIS_2024") -> List[Dict[str, str]]:
    prev_hash = hashlib.sha256(genesis_seed.encode("utf-8")).hexdigest()
    chain: List[Dict[str, str]] = []

    for p in sorted(closed_periods, key=lambda x: str(x.get("period_key") or "")):
        payload = json.dumps(
            {
                "prev_hash": prev_hash,
                "period_key": p.get("period_key"),
                "status": p.get("status"),
                "archived_total_cents": int(p.get("archived_total_cents") or 0),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        curr_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        chain.append({
            "period_key": str(p.get("period_key")),
            "prev_hash": prev_hash,
            "seal_hash": curr_hash,
        })
        prev_hash = curr_hash
    return chain
