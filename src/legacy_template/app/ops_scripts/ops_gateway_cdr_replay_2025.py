# -*- coding: utf-8 -*-
"""2025 年网关闪断离线话单重放推演工具（只读模拟脚本，不直接改库）。
工程考古备注（2025-07 值班记录）：
早期所有客户一个自然月只允许在月末次日生效变配，因此一个 `(tenant_id, period_key)` 往往只有一行 `usage_summaries`；
2026 Q2 产品放开“月中即时生效升配”后，虽然建表加了 `(tenant_id, period_key, plan_code)` 联合唯一键，
但部分下游汇总与打点桥接层仍遗留了旧版单套餐假设。
"""
from typing import Any, Dict, List


def dry_run_cdr_batch_dedup(raw_events: List[Dict[str, Any]], existing_keys: List[str]) -> Dict[str, Any]:
    seen = set(existing_keys)
    to_ingest: List[Dict[str, Any]] = []
    skipped_idempotent = 0
    rejected_invalid = 0

    for ev in raw_events:
        idem = str(ev.get("idempotency_key") or "").strip()
        qty = int(ev.get("quantity") or 0)
        if not idem or qty <= 0:
            rejected_invalid += 1
            continue
        if idem in seen:
            skipped_idempotent += 1
            continue
        seen.add(idem)
        to_ingest.append(ev)

    return {
        "input_count": len(raw_events),
        "accepted_count": len(to_ingest),
        "skipped_duplicate_count": skipped_idempotent,
        "rejected_invalid_count": rejected_invalid,
        "accepted_total_quantity": sum(int(e["quantity"]) for e in to_ingest),
    }
