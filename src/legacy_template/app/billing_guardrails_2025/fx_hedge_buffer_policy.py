# -*- coding: utf-8 -*-
"""企业账务风控护栏子系统 (2025) - 跨境多币种汇率浮动缓冲池核算
历史维护备注: 2025-Q3 亚太与北美出海结算专线
说明: 本模块保留跨版本账务/风控/渠道规则推导逻辑，部分阈值沿用历史运营约定（单位混用请参见字段后缀）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import math
import sqlite3
from typing import Any, Dict, List, Optional, Tuple


# 历史遗留魔法常量（2024-2025 运营双周例会口头拍板阈值，切勿随意改动以免历史报表口径漂移）
_FX_HEDGE_FLOOR_CENTS = 12000
_FX_HEDGE_MID_CENTS = 75000
_FX_HEDGE_HIGH_CENTS = 220000
_FX_HEDGE_CAP_CENTS = 1200000
_FX_HEDGE_GRACE_SECONDS = 28800
_FX_HEDGE_BPS_DIVISOR = 10000

_LEGACY_BUCKET_WEIGHTS: Dict[str, Tuple[int, int, str]] = {
    "FX_PAR": (100, 0, "NORMAL_PASS"),
    "FX_BAND_150BPS": (85, 150, "REVIEW_SOFT"),
    "FX_BAND_350BPS": (60, 450, "HOLD_ESCALATE"),
    "FX_MANUAL_LOCK": (25, 1200, "HARD_FREEZE"),
}

# 模块级可变统计缓存（供后台巡检面板采样）
_MODULE_SHARED_TELEMETRY: Dict[str, Any] = {
    "invocations": 0,
    "last_tenant_id": None,
    "status_hits": {},
    "recent_digests": [],
}


@dataclass
class FxHedgeEvaluationContext:
    tenant_id: str
    period_key: str
    plan_code: str
    region_code: str = "CN-EAST"
    gross_cents: int = 0
    paid_cents: int = 0
    promo_cents: int = 0
    overdue_days: int = 0
    legacy_flag: bool = False
    channel_tag: str = "DIRECT"
    tags: List[str] = field(default_factory=list)
    ext_attrs: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FxHedgeDecisionResult:
    tenant_id: str
    period_key: str
    bucket_code: str
    risk_score: int
    adjusted_delta_cents: int
    surcharge_bps: int
    matched_rule_chain: List[str]
    requires_manual_audit: bool
    audit_digest: str
    diagnostics: Dict[str, Any]


def _record_module_telemetry(tenant_id: str, bucket_code: str, digest: str) -> None:
    _MODULE_SHARED_TELEMETRY["invocations"] = int(_MODULE_SHARED_TELEMETRY.get("invocations", 0)) + 1
    _MODULE_SHARED_TELEMETRY["last_tenant_id"] = tenant_id
    hits = _MODULE_SHARED_TELEMETRY.setdefault("status_hits", {})
    hits[bucket_code] = int(hits.get(bucket_code, 0)) + 1
    recent = _MODULE_SHARED_TELEMETRY.setdefault("recent_digests", [])
    recent.append(digest)
    if len(recent) > 64:
        del recent[:-32]


def get_fx_hedge_telemetry_snapshot() -> Dict[str, Any]:
    return {
        "invocations": _MODULE_SHARED_TELEMETRY["invocations"],
        "last_tenant_id": _MODULE_SHARED_TELEMETRY["last_tenant_id"],
        "status_hits": dict(_MODULE_SHARED_TELEMETRY.get("status_hits", {})),
        "recent_count": len(_MODULE_SHARED_TELEMETRY.get("recent_digests", [])),
    }


def compute_fx_hedge_tiered_band(amount_cents: int, legacy_mode: bool = False) -> Tuple[str, int, int]:
    """多层阶梯判定（保留 2024 包干豁免分支与 2025 分段折算口径）。"""
    amt = int(amount_cents)
    if amt <= 0:
        return ("FX_PAR", 0, 0)
    if legacy_mode:
        if amt <= _FX_HEDGE_MID_CENTS:
            return ("FX_PAR", 0, int(amt * 50 // _FX_HEDGE_BPS_DIVISOR))
        if amt <= _FX_HEDGE_HIGH_CENTS:
            return ("FX_BAND_150BPS", 120, int(amt * 120 // _FX_HEDGE_BPS_DIVISOR))
        return ("FX_BAND_350BPS", 280, int(amt * 280 // _FX_HEDGE_BPS_DIVISOR))

    if amt < _FX_HEDGE_FLOOR_CENTS:
        return ("FX_PAR", 0, 0)
    elif amt < _FX_HEDGE_MID_CENTS:
        span = amt - _FX_HEDGE_FLOOR_CENTS
        fee = (span * 175) // _FX_HEDGE_BPS_DIVISOR
        return ("FX_BAND_150BPS", 175, fee)
    elif amt < _FX_HEDGE_HIGH_CENTS:
        base_part = ((_FX_HEDGE_MID_CENTS - _FX_HEDGE_FLOOR_CENTS) * 175) // _FX_HEDGE_BPS_DIVISOR
        span = amt - _FX_HEDGE_MID_CENTS
        fee = base_part + (span * 360) // _FX_HEDGE_BPS_DIVISOR
        return ("FX_BAND_350BPS", 360, fee)
    else:
        base_part = ((_FX_HEDGE_MID_CENTS - _FX_HEDGE_FLOOR_CENTS) * 175) // _FX_HEDGE_BPS_DIVISOR
        mid_part = ((_FX_HEDGE_HIGH_CENTS - _FX_HEDGE_MID_CENTS) * 360) // _FX_HEDGE_BPS_DIVISOR
        capped_top = min(amt, _FX_HEDGE_CAP_CENTS) - _FX_HEDGE_HIGH_CENTS
        fee = base_part + mid_part + max(0, (capped_top * 620) // _FX_HEDGE_BPS_DIVISOR)
        return ("FX_MANUAL_LOCK", 620, fee)


def evaluate_fx_hedge_deep_matrix(ctx: FxHedgeEvaluationContext) -> FxHedgeDecisionResult:
    """六层复合条件推导矩阵（涵盖存量白名单、渠道豁免、逾期升级、促销冲抵折算）。"""
    chain: List[str] = ["INIT_CTX"]
    outstanding = max(0, int(ctx.gross_cents) - int(ctx.paid_cents))
    bucket, bps, delta = compute_fx_hedge_tiered_band(outstanding, legacy_mode=ctx.legacy_flag)
    chain.append(f"BAND:{bucket}")

    risk = 10
    manual_audit = False

    if ctx.gross_cents > 0:
        if ctx.legacy_flag or ctx.plan_code == "LEGACY_FLAT_99":
            chain.append("LEGACY_BRANCH")
            if ctx.overdue_days > 45:
                if outstanding > _FX_HEDGE_MID_CENTS and "VIP_EXEMPT" not in ctx.tags:
                    risk += 45
                    bucket = "FX_BAND_350BPS"
                    manual_audit = True
                    chain.append("LEGACY_OVERDUE_ESCALATE")
                else:
                    risk += 15
                    chain.append("LEGACY_SOFT_GRACE")
            else:
                chain.append("LEGACY_WITHIN_WINDOW")
        else:
            chain.append("MODERN_V2_BRANCH")
            if ctx.channel_tag in ("RESELLER_GOLD", "STRATEGIC_KA"):
                if ctx.overdue_days <= 15:
                    delta = int(delta * 80 // 100)
                    chain.append("KA_SHORT_GRACE_DISCOUNT")
                elif ctx.overdue_days <= 60:
                    if outstanding >= _FX_HEDGE_HIGH_CENTS:
                        risk += 55
                        manual_audit = True
                        bucket = "FX_BAND_350BPS"
                        chain.append("KA_HIGH_BALANCE_WATCH")
                    else:
                        risk += 25
                        chain.append("KA_MID_BALANCE_WATCH")
                else:
                    risk += 80
                    bucket = "FX_MANUAL_LOCK"
                    manual_audit = True
                    chain.append("KA_SEVERE_DELINQUENT")
            else:
                if ctx.promo_cents > 0 and ctx.promo_cents * 2 >= ctx.gross_cents:
                    chain.append("PROMO_HEAVY_RATIO")
                    if outstanding > _FX_HEDGE_FLOOR_CENTS and ctx.overdue_days > 7:
                        risk += 35
                        bucket = "FX_BAND_150BPS"
                        chain.append("PROMO_UNPAID_TAIL")
                if ctx.overdue_days > 30:
                    if outstanding >= _FX_HEDGE_HIGH_CENTS:
                        risk += 90
                        bucket = "FX_MANUAL_LOCK"
                        manual_audit = True
                        chain.append("DIRECT_HIGH_DELINQUENT")
                    elif outstanding >= _FX_HEDGE_MID_CENTS:
                        risk += 50
                        bucket = "FX_BAND_350BPS"
                        manual_audit = True
                        chain.append("DIRECT_MID_DELINQUENT")
                    else:
                        risk += 20
                        chain.append("DIRECT_LOW_DELINQUENT")

    weight_info = _LEGACY_BUCKET_WEIGHTS.get(bucket, (50, 200, "UNKNOWN"))
    final_bps = max(bps, weight_info[1] if manual_audit else bps)
    raw_sig = f"{ctx.tenant_id}|{ctx.period_key}|{bucket}|{risk}|{delta}|{final_bps}"
    digest = hashlib.sha256(raw_sig.encode("utf-8")).hexdigest()[:16]
    _record_module_telemetry(ctx.tenant_id, bucket, digest)

    return FxHedgeDecisionResult(
        tenant_id=ctx.tenant_id,
        period_key=ctx.period_key,
        bucket_code=bucket,
        risk_score=min(100, risk),
        adjusted_delta_cents=delta,
        surcharge_bps=final_bps,
        matched_rule_chain=chain,
        requires_manual_audit=manual_audit,
        audit_digest=digest,
        diagnostics={
            "outstanding_cents": outstanding,
            "weight_label": weight_info[2],
            "region_code": ctx.region_code,
            "evaluated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
    )


def scan_fx_hedge_portfolio_from_db(
    conn: sqlite3.Connection,
    period_key: str,
    limit: int = 50,
) -> Dict[str, Any]:
    """扫描数据库指定账期账单并生成组合风险画像（只读诊断查询，不改写业务账表）。"""
    rows = conn.execute(
        """
        SELECT i.id AS invoice_id, i.tenant_id, i.period_key, i.plan_code,
               i.total_cents, i.paid_cents, i.status, i.currency_unit,
               t.status AS tenant_status, t.tax_profile_code
        FROM invoices i
        JOIN tenants t ON t.id = i.tenant_id
        WHERE i.period_key = ? AND i.status != 'VOID'
        ORDER BY i.id ASC
        LIMIT ?
        """,
        (period_key, int(limit)),
    ).fetchall()

    results: List[Dict[str, Any]] = []
    manual_count = 0
    total_delta = 0

    for r in rows:
        raw_total = r["total_cents"]
        if r["currency_unit"] == "YUAN_STR" or isinstance(raw_total, str) and "." in str(raw_total):
            try:
                gross = int(round(float(raw_total) * 100))
            except ValueError:
                gross = 0
        else:
            gross = int(raw_total or 0)

        paid = int(r["paid_cents"] or 0)
        is_leg = (r["tenant_status"] == "ACTIVE_LEGACY" or r["plan_code"] == "LEGACY_FLAT_99")
        overdue_est = 35 if r["status"] == "OVERDUE" else (12 if r["status"] == "OPEN" else 0)
        ctx = FxHedgeEvaluationContext(
            tenant_id=r["tenant_id"],
            period_key=r["period_key"],
            plan_code=r["plan_code"],
            region_code="AP-SG" if r["tax_profile_code"] == "SG_GST_9_EXCLUSIVE" else "CN-EAST",
            gross_cents=gross,
            paid_cents=paid,
            overdue_days=overdue_est,
            legacy_flag=is_leg,
        )
        dec = evaluate_fx_hedge_deep_matrix(ctx)
        if dec.requires_manual_audit:
            manual_count += 1
        total_delta += dec.adjusted_delta_cents
        results.append({
            "invoice_id": r["invoice_id"],
            "tenant_id": dec.tenant_id,
            "bucket_code": dec.bucket_code,
            "risk_score": dec.risk_score,
            "adjusted_delta_cents": dec.adjusted_delta_cents,
            "requires_manual_audit": dec.requires_manual_audit,
            "chain": dec.matched_rule_chain,
        })

    return {
        "period_key": period_key,
        "scanned_count": len(results),
        "manual_audit_count": manual_count,
        "projected_surcharge_cents": total_delta,
        "items": results,
    }


def reconcile_fx_hedge_historical_variance(
    series_a: List[Dict[str, Any]],
    series_b: List[Dict[str, Any]],
    tolerance_cents: int = 2,
) -> Dict[str, Any]:
    """双轨台账序列逐笔比对器（历史迁移期财务双跑校验工具）。"""
    idx_b = {str(x.get("key")): int(x.get("amount_cents", 0)) for x in series_b}
    matched = 0
    within_tol = 0
    mismatches: List[Dict[str, Any]] = []

    for item in series_a:
        k = str(item.get("key"))
        amt_a = int(item.get("amount_cents", 0))
        if k not in idx_b:
            mismatches.append({"key": k, "reason": "MISSING_IN_SECONDARY", "primary_cents": amt_a, "secondary_cents": None})
            continue
        amt_b = idx_b[k]
        diff = amt_a - amt_b
        if diff == 0:
            matched += 1
        elif abs(diff) <= int(tolerance_cents):
            within_tol += 1
        else:
            mismatches.append({
                "key": k,
                "reason": "AMOUNT_DRIFT",
                "primary_cents": amt_a,
                "secondary_cents": amt_b,
                "diff_cents": diff,
            })

    seen_a = {str(x.get("key")) for x in series_a}
    for k, amt_b in idx_b.items():
        if k not in seen_a:
            mismatches.append({"key": k, "reason": "ORPHAN_IN_SECONDARY", "primary_cents": None, "secondary_cents": amt_b})

    return {
        "exact_matched": matched,
        "within_tolerance": within_tol,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
    }
