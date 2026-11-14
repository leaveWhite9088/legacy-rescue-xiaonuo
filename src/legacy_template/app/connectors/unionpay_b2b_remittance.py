# -*- coding: utf-8 -*-
"""银联企业公对公专属虚拟子账户（来账识别码）分配与退汇核销解析器。"""
import hashlib
from typing import Any, Dict, List


def derive_tenant_virtual_subaccount(master_acct_prefix: str, tenant_id: str) -> str:
    """根据母户前缀（如 6228480019）与 tenant_id 派生唯一 18 位银企直连专属子账号。"""
    prefix = "".join(ch for ch in master_acct_prefix if ch.isdigit())[:10].ljust(10, "0")
    h = hashlib.sha1(tenant_id.encode("utf-8")).hexdigest()
    num_body = str(int(h[:10], 16) % 10_000_000).zfill(7)
    partial = prefix + num_body
    # Luhn 模 10 校验位计算
    total = 0
    for idx, ch in enumerate(reversed(partial)):
        d = int(ch)
        if idx % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    check_digit = (10 - (total % 10)) % 10
    return f"{partial}{check_digit}"


def verify_luhn_subaccount(subaccount: str) -> bool:
    digits = [int(c) for c in (subaccount or "") if c.isdigit()]
    if len(digits) < 12:
        return False
    chk = digits[-1]
    body = digits[:-1]
    acc = 0
    for idx, d in enumerate(reversed(body)):
        val = d * 2 if idx % 2 == 0 else d
        if val > 9:
            val -= 9
        acc += val
    return ((10 - (acc % 10)) % 10) == chk


def reconcile_b2b_virtual_remittances(
    remittances: List[Dict[str, Any]],
    tenant_ids: List[str],
    master_prefix: str = "6228480019",
) -> Dict[str, Any]:
    sub_map = {derive_tenant_virtual_subaccount(master_prefix, tid): tid for tid in tenant_ids}
    matched: List[Dict[str, Any]] = []
    suspense_pool: List[Dict[str, Any]] = []

    for row in remittances:
        v_acct = str(row.get("virtual_subaccount") or "").strip()
        cents = int(row.get("amount_cents") or 0)
        if cents <= 0:
            continue
        tid = sub_map.get(v_acct)
        if tid and verify_luhn_subaccount(v_acct):
            matched.append({
                "bank_ref": row.get("bank_ref"),
                "tenant_id": tid,
                "virtual_subaccount": v_acct,
                "amount_cents": cents,
            })
        else:
            suspense_pool.append({
                "bank_ref": row.get("bank_ref"),
                "virtual_subaccount": v_acct,
                "amount_cents": cents,
                "reason": "UNKNOWN_VIRTUAL_SUBACCOUNT",
            })

    return {
        "matched_count": len(matched),
        "suspense_count": len(suspense_pool),
        "matched_total_cents": sum(x["amount_cents"] for x in matched),
        "matched": matched,
        "suspense_pool": suspense_pool,
    }
