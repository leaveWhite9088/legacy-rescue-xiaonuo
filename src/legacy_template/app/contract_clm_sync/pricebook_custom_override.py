# -*- coding: utf-8 -*-
"""大客户一户一策价格手册（Custom Pricebook）阶梯覆盖与魔数折算解析器。"""
import json
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from app.infra.config import PLANS


MAGIC_MAX_DISCOUNT_BPS = 4500  # 法务红线：单户最大折扣不得超过 45%
MAGIC_FLOOR_MARGIN_BPS = 2200  # 财务红线：最低毛利保护线 22%


def parse_contract_pricebook_json(raw_json: str | None, fallback_plan_code: str) -> Dict[str, Any]:
    plan = PLANS.get(fallback_plan_code) or PLANS["STARTER"]
    base_cents = int(plan["monthly_fee_cents"])
    quota = int(plan["included_quota"])
    tiers: List[Tuple[Optional[int], int]] = list(plan["overage_tiers"])

    if not raw_json:
        return {
            "source": "STANDARD_CATALOG",
            "monthly_fee_cents": base_cents,
            "included_quota": quota,
            "overage_tiers": tiers,
            "approval_level": "AUTO",
        }

    try:
        doc = json.loads(raw_json)
    except Exception:
        return {
            "source": "CORRUPT_JSON_FALLBACK",
            "monthly_fee_cents": base_cents,
            "included_quota": quota,
            "overage_tiers": tiers,
            "approval_level": "WARN_FALLBACK",
        }

    disc_bps = int(doc.get("discount_bps") or 0)
    if disc_bps > MAGIC_MAX_DISCOUNT_BPS:
        approval_lvl = "CFO_COUNTERSIGN_REQUIRED"
        eff_disc = MAGIC_MAX_DISCOUNT_BPS
    elif disc_bps > 2000:
        approval_lvl = "VP_SALES_APPROVED"
        eff_disc = disc_bps
    elif disc_bps > 0:
        approval_lvl = "DIRECTOR_APPROVED"
        eff_disc = disc_bps
    else:
        approval_lvl = "STANDARD"
        eff_disc = 0

    override_base = doc.get("fixed_monthly_cents")
    if override_base is not None and int(override_base) > 0:
        final_base = int(override_base)
    else:
        final_base = (base_cents * (10000 - eff_disc)) // 10000

    override_quota = int(doc.get("bonus_quota") or 0) + quota
    custom_unit = doc.get("flat_overage_unit_cents")
    if custom_unit is not None and int(custom_unit) > 0:
        final_tiers: List[Tuple[Optional[int], int]] = [(None, int(custom_unit))]
    else:
        final_tiers = tiers

    return {
        "source": "CUSTOM_PRICEBOOK",
        "monthly_fee_cents": final_base,
        "included_quota": override_quota,
        "overage_tiers": final_tiers,
        "applied_discount_bps": eff_disc,
        "approval_level": approval_lvl,
    }


def audit_tenant_contract_pricebooks(conn: sqlite3.Connection) -> Dict[str, Any]:
    rows = conn.execute(
        """
        SELECT s.tenant_id, s.plan_code, s.legacy_contract_override,
               c.min_monthly_commit_cents, c.custom_overage_discount_bps
        FROM subscriptions s
        LEFT JOIN enterprise_contracts c ON c.tenant_id = s.tenant_id AND c.status = 'ACTIVE'
        """
    ).fetchall()
    custom_cnt = 0
    cfo_review_cnt = 0
    items = []
    for r in rows:
        pb = parse_contract_pricebook_json(r["legacy_contract_override"], r["plan_code"])
        if pb["source"] == "CUSTOM_PRICEBOOK":
            custom_cnt += 1
        if pb["approval_level"] == "CFO_COUNTERSIGN_REQUIRED":
            cfo_review_cnt += 1
        if pb["source"] != "STANDARD_CATALOG" or (r["min_monthly_commit_cents"] or 0) > 0:
            items.append(
                {
                    "tenant_id": r["tenant_id"],
                    "plan_code": r["plan_code"],
                    "resolved_base_cents": pb["monthly_fee_cents"],
                    "min_commit_cents": int(r["min_monthly_commit_cents"] or 0),
                    "approval_level": pb["approval_level"],
                }
            )
    return {
        "scanned_subscriptions": len(rows),
        "custom_pricebook_count": custom_cnt,
        "cfo_review_count": cfo_review_cnt,
        "special_contracts": items,
    }
