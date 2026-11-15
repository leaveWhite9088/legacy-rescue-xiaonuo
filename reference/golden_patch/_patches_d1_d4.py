#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""黄金补丁分卷一：业务域 1 ~ 业务域 4 外科手术修复（BUG-01 ~ BUG-31）。"""
from pathlib import Path


def replace_exact(base: Path, rel_path: str, target: str, replacement: str) -> None:
    p = base / rel_path
    text = p.read_text(encoding="utf-8")
    norm_text = text.replace("\r\n", "\n")
    norm_target = target.replace("\r\n", "\n")
    norm_repl = replacement.replace("\r\n", "\n")
    if norm_target not in norm_text:
        raise RuntimeError(f"[GoldenPatch] Target snippet not found in {rel_path}:\n{norm_target[:220]}")
    p.write_text(norm_text.replace(norm_target, norm_repl, 1), encoding="utf-8", newline="\n")


def apply_d1_metering_pricing(base: Path) -> None:
    # BUG-01: 变配钩子驱逐真实配额快照缓存 + 双写缓冲记录事件发生时套餐 + 刷盘优先使用快照套餐
    replace_exact(
        base,
        "app/hooks/lifecycle_hooks.py",
        """from app.infra.cache import contract_cache
from app.infra.events import event_bus
from app.infra.metrics_collector import runtime_metrics
from app.legacy_v1.v1_quota_memcached_emu import v1_dead_quota_slab


def on_subscription_plan_changed(payload: dict) -> None:
    \"\"\"处理订阅变配事件：上报监控计数并刷新框架合同与配额槽缓存。\"\"\"
    tid = payload.get("tenant_id")
    runtime_metrics.inc("domain.subscription.plan_changed")
    if tid:
        contract_cache.delete(f"contract:{tid}")
        v1_dead_quota_slab.delete(f"v1_quota:{tid}")""",
        """from app.compat.quota_cache_shim import evict_cached_plan_snapshot
from app.infra.cache import contract_cache
from app.infra.events import event_bus
from app.infra.metrics_collector import runtime_metrics
from app.legacy_v1.v1_quota_memcached_emu import v1_dead_quota_slab


def on_subscription_plan_changed(payload: dict) -> None:
    \"\"\"处理订阅变配事件：上报监控计数并刷新框架合同与配额槽缓存。\"\"\"
    tid = payload.get("tenant_id")
    runtime_metrics.inc("domain.subscription.plan_changed")
    if tid:
        contract_cache.delete(f"contract:{tid}")
        v1_dead_quota_slab.delete(f"v1_quota:{tid}")
        evict_cached_plan_snapshot(tid)""",
    )
    replace_exact(
        base,
        "app/compat/usage_dual_write_shim.py",
        "        plan_code_at_event=None,",
        "        plan_code_at_event=resolved_plan_code,",
    )
    replace_exact(
        base,
        "app/compat/v1_v2_bridge.py",
        """def resolve_flush_plan_code(conn: sqlite3.Connection, event_row: sqlite3.Row) -> str:
    \"\"\"刷盘时解析计量事件应归入的套餐分段代码。\"\"\"
    tenant_id = event_row["tenant_id"]""",
        """def resolve_flush_plan_code(conn: sqlite3.Connection, event_row: sqlite3.Row) -> str:
    \"\"\"刷盘时解析计量事件应归入的套餐分段代码。\"\"\"
    snap = event_row["plan_code_at_event"] if "plan_code_at_event" in event_row.keys() else None
    if snap and str(snap).strip():
        return str(snap).strip()
    tenant_id = event_row["tenant_id"]""",
    )

    # BUG-02, BUG-03, BUG-07: 分段各自配额超额核算 + 自定义阶梯差一修正 + 升级补差先乘后除 + 协议有效期校验
    replace_exact(
        base,
        "app/domain/pricing.py",
        "            band_span = max(0, int(cum_upper) - prev_upper - 1)",
        "            band_span = max(0, int(cum_upper) - prev_upper)",
    )
    replace_exact(
        base,
        "app/domain/pricing.py",
        "    return (int(days_remaining) // int(cycle_days)) * diff",
        "    return (int(days_remaining) * diff) // int(cycle_days)",
    )
    replace_exact(
        base,
        "app/domain/pricing.py",
        """def _compute_v2_merged_overage(breakdown: List[Dict[str, Any]], current_plan_code: str) -> int:
    \"\"\"v2 默认超额汇聚逻辑：将账期内各行用量累加为单一总量后套用期末当前套餐阶梯。\"\"\"
    total_usage = sum(int(r["total_quantity"]) for r in breakdown)
    plan = PLANS[current_plan_code]
    return compute_tiered_overage_cents(
        total_usage,
        int(plan["included_quota"]),
        plan["overage_tiers"],
    )""",
        """def _compute_v2_merged_overage(breakdown: List[Dict[str, Any]], current_plan_code: str) -> int:
    \"\"\"按各套餐分段独立核扣各自套餐包含配额与阶梯并求和。\"\"\"
    total_overage = 0
    for r in breakdown:
        seg_plan = PLANS.get(r["plan_code"], PLANS[current_plan_code])
        total_overage += compute_tiered_overage_cents(
            int(r["total_quantity"]),
            int(seg_plan["included_quota"]),
            seg_plan["overage_tiers"],
        )
    return total_overage""",
    )
    replace_exact(
        base,
        "app/domain/pricing.py",
        """    contract_res = apply_enterprise_contract_terms(
        conn,
        tenant_id,
        base_fee_cents=base_fee,
        overage_fee_cents=raw_overage,
    )""",
        """    contract_res = apply_enterprise_contract_terms(
        conn,
        tenant_id,
        base_fee_cents=base_fee,
        overage_fee_cents=raw_overage,
        as_of_iso=f"{period_key}-15T00:00:00Z",
    )""",
    )

    # BUG-03: 动态布尔配置解析字符串 'false'/'0'
    replace_exact(
        base,
        "app/infra/runtime_config_loader.py",
        "            return bool(row[\"config_value\"])",
        "            return str(row[\"config_value\"]).strip().lower() in (\"1\", \"true\", \"yes\", \"on\")",
    )

    # BUG-04 & BUG-05: 拦截 <=0 非法用量 + 时区归一至 UTC 账期 + 完整幂等键及 DB 去重
    replace_exact(
        base,
        "app/services/metering_service.py",
        """    except (TypeError, ValueError):
        raise ValueError("quantity 必须为整数")""",
        """    except (TypeError, ValueError):
        raise ValueError("quantity 必须为整数")
    if quantity <= 0:
        raise ValueError("quantity 必须为正整数")""",
    )
    replace_exact(
        base,
        "app/gateway_ingest/idempotency_bloom_cache.py",
        "        slot_key = clean[:8]",
        "        slot_key = clean",
    )
    replace_exact(
        base,
        "app/gateway_ingest/batch_ingest_service.py",
        """        if qty < 0:
            raise ValueError("批量事件 quantity 不允许为负数")

        raw_ts = str(item.get("occurred_at") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")).strip()
        # 截取前 7 位作为归属账期
        derived_period_key = str(item.get("period_key") or raw_ts[:7])
        eid = str(item.get("event_id") or f"ue_b_{uuid.uuid4().hex[:12]}").strip()
        metric = str(item.get("metric_code") or "API_CALLS")

        if item.get("event_id") and default_ingest_ring.seen_or_record(eid):
            duplicates += 1
            continue""",
        """        if qty <= 0:
            raise ValueError("批量事件 quantity 必须为正整数")

        raw_ts = str(item.get("occurred_at") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")).strip()
        if item.get("period_key"):
            derived_period_key = str(item["period_key"]).strip()
        else:
            dt_utc = datetime.fromisoformat(raw_ts.replace("Z", "+00:00")).astimezone(timezone.utc)
            derived_period_key = dt_utc.strftime("%Y-%m")
        eid = str(item.get("event_id") or f"ue_b_{uuid.uuid4().hex[:12]}").strip()
        metric = str(item.get("metric_code") or "API_CALLS")

        if item.get("event_id"):
            exists_db = conn.execute("SELECT 1 FROM usage_events WHERE id = ?", (eid,)).fetchone()
            if exists_db or default_ingest_ring.seen_or_record(eid):
                duplicates += 1
                continue""",
    )

    # BUG-06: 多地域分片归并累加而非覆盖 + 拦截 <=0 非法分片用量
    replace_exact(
        base,
        "app/gateway_ingest/cross_region_shard_merger.py",
        """        qty = int(rec.get("quantity", 0))
        raw_ts = str(rec.get("occurred_at") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")).strip()
        period_key = str(rec.get("period_key") or raw_ts[:7])
        metric = str(rec.get("metric_code") or "API_CALLS")
        # 按分片批次键同步最新区域采集快照值
        merged_buckets[(period_key, metric)] = qty""",
        """        qty = int(rec.get("quantity", 0))
        if qty <= 0:
            raise ValueError("分片上报 quantity 必须大于 0")
        raw_ts = str(rec.get("occurred_at") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")).strip()
        period_key = str(rec.get("period_key") or raw_ts[:7])
        metric = str(rec.get("metric_code") or "API_CALLS")
        merged_buckets[(period_key, metric)] = merged_buckets.get((period_key, metric), 0) + qty""",
    )

    # BUG-07: credit_memo_bps 折让不得击穿最低月度保底额 min_monthly_commit_cents
    replace_exact(
        base,
        "app/domain/contracts.py",
        "        floored_sub = max(0, floored_sub - apply_bps(floored_sub, memo_bps))",
        "        floored_sub = max(min_commit, floored_sub - apply_bps(floored_sub, memo_bps))",
    )

    # BUG-08: SLA 极端故障赔付上限 100% (10000 bps) + 扫描任务完成后扭转状态为 CREDITED/MEETS_SLA 防重签
    replace_exact(
        base,
        "app/domain/sla_calculator.py",
        "        comp_bps = 15000",
        "        comp_bps = 10000",
    )
    replace_exact(
        base,
        "app/jobs/sla_credit_scan_job.py",
        """        conn.execute(
            "UPDATE sla_credit_claims SET credit_cents = ?, status = 'EVALUATED', created_at = ? WHERE id = ?",
            (res["credit_cents"], now, r["id"]),
        )""",
        """        final_st = "CREDITED" if res["credit_cents"] > 0 else "MEETS_SLA"
        conn.execute(
            "UPDATE sla_credit_claims SET credit_cents = ?, status = ?, created_at = ? WHERE id = ?",
            (res["credit_cents"], final_st, now, r["id"]),
        )""",
    )

    # BUG-09: 资费代理深拷贝防共享污染 + 可变默认列表修复
    replace_exact(
        base,
        "app/enterprise_catalog_rules/tariff_strategy_chain.py",
        """from abc import ABC, abstractmethod
from typing import Any, Dict""",
        """from abc import ABC, abstractmethod
import copy
from typing import Any, Dict""",
    )
    replace_exact(
        base,
        "app/enterprise_catalog_rules/tariff_strategy_chain.py",
        "        return self._cache[key]",
        "        return copy.deepcopy(self._cache[key])",
    )
    replace_exact(
        base,
        "app/billing_ext/custom_price_book_overrides.py",
        """def compile_tenant_price_book_override(
    plan_code: str,
    discount_bps: int = 0,
    audit_trail: List[str] = [],
) -> Dict[str, Any]:
    \"\"\"根据标准套餐与协议折扣生成租户专属价目表快照。\"\"\"
    spec = PLANS.get(plan_code, PLANS["STARTER"])
    base = int(spec["monthly_fee_cents"])
    net_base = max(0, base - (base * int(discount_bps)) // 10000)
    audit_trail.append(f"override:{plan_code}:bps={discount_bps}")
    return {
        "plan_code": plan_code,
        "base_fee_cents": base,
        "effective_base_fee_cents": net_base,
        "discount_bps": int(discount_bps),
        "audit_trail": audit_trail,
    }""",
        """def compile_tenant_price_book_override(
    plan_code: str,
    discount_bps: int = 0,
    audit_trail: Optional[List[str]] = None,
) -> Dict[str, Any]:
    \"\"\"根据标准套餐与协议折扣生成租户专属价目表快照。\"\"\"
    spec = PLANS.get(plan_code, PLANS["STARTER"])
    base = int(spec["monthly_fee_cents"])
    net_base = max(0, base - (base * int(discount_bps)) // 10000)
    trail = list(audit_trail) if audit_trail is not None else []
    trail.append(f"override:{plan_code}:bps={discount_bps}")
    return {
        "plan_code": plan_code,
        "base_fee_cents": base,
        "effective_base_fee_cents": net_base,
        "discount_bps": int(discount_bps),
        "audit_trail": trail,
    }""",
    )


def apply_d2_wallet_settlement(base: Path) -> None:
    # BUG-10 & BUG-17: 退款原路分桶退回 + 预览只读不锁券、扣减已付且严格校验租户归属
    replace_exact(
        base,
        "app/compat/wallet_bridge.py",
        "    legacy_fast_cash_mode: bool = True,",
        "    legacy_fast_cash_mode: bool = False,",
    )
    replace_exact(
        base,
        "app/compat/wallet_bridge.py",
        """    if inv["tenant_id"] != tenant_id and inv["status"] == "VOID":
        raise PermissionError("无权预览其他租户已作废账单")

    due_cents = max(0, int(inv["total_cents"]))
    wallet = conn.execute("SELECT * FROM wallets WHERE tenant_id = ?", (tenant_id,)).fetchone()
    avail_promo = max(0, int(wallet["promo_balance_cents"])) if wallet else 0
    avail_cash = max(0, int(wallet["cash_balance_cents"])) if wallet else 0

    promo_est = min(avail_promo, due_cents)
    cash_est = max(0, due_cents - promo_est)

    # 标记券批次试算占用状态供前端提示
    if promo_est > 0:
        conn.execute(
            "UPDATE promo_grants SET status = 'LOCKED_PREVIEW' WHERE tenant_id = ? AND status = 'ACTIVE'",
            (tenant_id,),
        )""",
        """    if inv["tenant_id"] != tenant_id:
        raise PermissionError("无权预览其他租户账单")

    due_cents = max(0, int(inv["total_cents"]) - int(inv["paid_cents"]))
    wallet = conn.execute("SELECT * FROM wallets WHERE tenant_id = ?", (tenant_id,)).fetchone()
    avail_promo = max(0, int(wallet["promo_balance_cents"])) if wallet else 0
    avail_cash = max(0, int(wallet["cash_balance_cents"])) if wallet else 0

    promo_est = min(avail_promo, due_cents)
    cash_est = max(0, due_cents - promo_est)""",
    )

    # BUG-10, BUG-11, BUG-12, BUG-44 (in ledger.py + routes/billing.py)
    replace_exact(
        base,
        "app/routes/billing.py",
        """    try:
        with tx_context(db_path) as conn:
            res = facade_pay_invoice(conn, g.tenant["id"], invoice_id, idempotency_key=idem_key)""",
        """    try:
        with tx_context(db_path, immediate=True) as conn:
            res = facade_pay_invoice(conn, g.tenant["id"], invoice_id, idempotency_key=idem_key)""",
    )
    replace_exact(
        base,
        "app/domain/ledger.py",
        """    if idempotency_key:
        dup = conn.execute(
            "SELECT * FROM invoice_payments WHERE idempotency_key = ? LIMIT 1",
            (idempotency_key,),
        ).fetchone()
        if dup:
            return {
                "payment_id": dup["id"],
                "invoice_id": dup["invoice_id"],
                "cash_paid_cents": dup["cash_paid_cents"],
                "promo_paid_cents": dup["promo_paid_cents"],
                "total_paid_cents": dup["total_paid_cents"],
                "status": "PAID",
            }

    due_cents = int(inv["total_cents"]) - int(inv["paid_cents"])
    if due_cents <= 0:
        return {"invoice_id": invoice_id, "status": inv["status"], "paid_cents": 0}

    wallet = get_wallet(conn, tenant_id)
    avail_promo = max(0, int(wallet["promo_balance_cents"]))
    avail_cash = max(0, int(wallet["cash_balance_cents"]))
    if avail_promo + avail_cash < due_cents:
        raise ValueError("钱包余额不足")

    promo_used = min(avail_promo, due_cents)
    cash_used = due_cents - promo_used
    now = _now_iso()

    rem_to_consume = promo_used
    if rem_to_consume > 0:
        grants = conn.execute(
            "SELECT * FROM promo_grants WHERE tenant_id = ? AND status = 'ACTIVE' AND remaining_cents > 0 ORDER BY expires_at DESC",
            (tenant_id,),
        ).fetchall()""",
        """    scoped_idem = f"{tenant_id}:{invoice_id}:{idempotency_key}" if idempotency_key else None
    if idempotency_key:
        dup = conn.execute(
            "SELECT * FROM invoice_payments WHERE tenant_id = ? AND invoice_id = ? AND idempotency_key IN (?, ?) LIMIT 1",
            (tenant_id, invoice_id, scoped_idem, idempotency_key),
        ).fetchone()
        if dup:
            return {
                "payment_id": dup["id"],
                "invoice_id": dup["invoice_id"],
                "cash_paid_cents": dup["cash_paid_cents"],
                "promo_paid_cents": dup["promo_paid_cents"],
                "total_paid_cents": dup["total_paid_cents"],
                "status": "PAID",
            }

    due_cents = int(inv["total_cents"]) - int(inv["paid_cents"])
    if due_cents <= 0:
        return {"invoice_id": invoice_id, "status": inv["status"], "paid_cents": 0}

    now = _now_iso()
    valid_grants = conn.execute(
        "SELECT * FROM promo_grants WHERE tenant_id = ? AND status = 'ACTIVE' AND remaining_cents > 0 AND expires_at > ? ORDER BY expires_at ASC",
        (tenant_id, now),
    ).fetchall()
    grant_promo_cap = sum(int(g["remaining_cents"]) for g in valid_grants)

    wallet = get_wallet(conn, tenant_id)
    avail_promo = min(max(0, int(wallet["promo_balance_cents"])), grant_promo_cap)
    avail_cash = max(0, int(wallet["cash_balance_cents"]))
    if avail_promo + avail_cash < due_cents:
        raise ValueError("钱包余额不足")

    promo_used = min(avail_promo, due_cents)
    cash_used = due_cents - promo_used

    rem_to_consume = promo_used
    if rem_to_consume > 0:
        grants = valid_grants""",
    )
    replace_exact(
        base,
        "app/domain/ledger.py",
        "(pay_id, invoice_id, tenant_id, idempotency_key, cash_used, promo_used, due_cents, now),",
        "(pay_id, invoice_id, tenant_id, scoped_idem, cash_used, promo_used, due_cents, now),",
    )
    replace_exact(
        base,
        "app/domain/ledger.py",
        "    resolve_dunning_for_invoice(conn, invoice_id, now)",
        """    resolve_dunning_for_invoice(conn, invoice_id, now)
    rem_open_dun = conn.execute(
        "SELECT COUNT(*) FROM dunning_cases WHERE tenant_id = ? AND status = 'OPEN'",
        (tenant_id,),
    ).fetchone()[0]
    if int(rem_open_dun) == 0:
        conn.execute("UPDATE tenants SET status = 'ACTIVE' WHERE id = ? AND status = 'SUSPENDED'", (tenant_id,))
        conn.execute("UPDATE subscriptions SET status = 'ACTIVE', updated_at = ? WHERE tenant_id = ? AND status = 'SUSPENDED'", (now, tenant_id))""",
    )
    replace_exact(
        base,
        "app/domain/ledger.py",
        """    append_wallet_ledger(conn, tenant_id, "REFUND", cash_back, promo_back, invoice_id, reason, now)""",
        """    if promo_back > 0:
        rem_restore = promo_back
        g_rows = conn.execute(
            "SELECT * FROM promo_grants WHERE tenant_id = ? AND status IN ('ACTIVE', 'EXHAUSTED') AND expires_at > ? ORDER BY expires_at DESC",
            (tenant_id, now),
        ).fetchall()
        for g in g_rows:
            if rem_restore <= 0:
                break
            headroom = max(0, int(g["initial_cents"]) - int(g["remaining_cents"]))
            add_amt = min(rem_restore, headroom) if headroom > 0 else 0
            if add_amt > 0:
                conn.execute(
                    "UPDATE promo_grants SET remaining_cents = remaining_cents + ?, status = 'ACTIVE' WHERE id = ?",
                    (add_amt, g["id"]),
                )
                rem_restore -= add_amt
    append_wallet_ledger(conn, tenant_id, "REFUND", cash_back, promo_back, invoice_id, reason, now)""",
    )
    replace_exact(
        base,
        "app/domain/ledger.py",
        """    rows = conn.execute(
        "SELECT * FROM promo_grants WHERE expires_at <= ?",
        (cutoff,),
    ).fetchall()
    expired_count = 0
    total_deducted = 0
    for g in rows:
        deduct = int(g["initial_cents"])
        conn.execute(
            "UPDATE wallets SET promo_balance_cents = promo_balance_cents - ?, updated_at = ? WHERE tenant_id = ?",
            (deduct, cutoff, g["tenant_id"]),
        )""",
        """    rows = conn.execute(
        "SELECT * FROM promo_grants WHERE expires_at <= ? AND status != 'EXPIRED'",
        (cutoff,),
    ).fetchall()
    expired_count = 0
    total_deducted = 0
    for g in rows:
        deduct = max(0, int(g["remaining_cents"]))
        conn.execute(
            "UPDATE wallets SET promo_balance_cents = MAX(0, promo_balance_cents - ?), updated_at = ? WHERE tenant_id = ?",
            (deduct, cutoff, g["tenant_id"]),
        )""",
    )

    # BUG-13, BUG-14, BUG-15, BUG-16, BUG-18
    replace_exact(
        base,
        "app/repos/subscription_repo.py",
        "        WHERE s.status IN ('ACTIVE', 'ACTIVE_LEGACY')",
        "        WHERE s.status IN ('ACTIVE', 'ACTIVE_LEGACY')\n          AND t.status IN ('ACTIVE', 'ACTIVE_LEGACY')",
    )
    replace_exact(
        base,
        "app/services/subscription_service.py",
        """    now = _now_iso()
    period_key = sub["cycle_end"][:7]
    bill = calculate_cycle_bill(conn, tenant_id, period_key, sub["plan_code"])""",
        """    now = _now_iso()
    period_key = sub["cycle_start"][:7]
    existing_inv = conn.execute(
        "SELECT id, total_cents FROM invoices WHERE tenant_id = ? AND period_key = ? AND status != 'VOID' LIMIT 1",
        (tenant_id, period_key),
    ).fetchone()
    if existing_inv:
        return {"invoice_id": existing_inv["id"], "period_key": period_key, "total_cents": existing_inv["total_cents"]}
    bill = calculate_cycle_bill(conn, tenant_id, period_key, sub["plan_code"])""",
    )
    replace_exact(
        base,
        "app/jobs/settlement_job.py",
        """        tenant_id = sub["tenant_id"]
        period_key = sub["cycle_end"][:7]
        bill = calculate_cycle_bill(conn, tenant_id, period_key, sub["plan_code"])""",
        """        tenant_id = sub["tenant_id"]
        period_key = sub["cycle_start"][:7]
        dup_inv = conn.execute(
            "SELECT id FROM invoices WHERE tenant_id = ? AND period_key = ? AND status != 'VOID' LIMIT 1",
            (tenant_id, period_key),
        ).fetchone()
        if dup_inv:
            old_end = datetime.fromisoformat(sub["cycle_end"].replace("Z", "+00:00"))
            new_end = (old_end + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
            conn.execute(
                "UPDATE subscriptions SET cycle_start = ?, cycle_end = ?, next_billing_at = ?, updated_at = ? WHERE id = ?",
                (old_end.strftime("%Y-%m-%dT%H:%M:%SZ"), new_end, new_end, now, sub["id"]),
            )
            continue
        bill = calculate_cycle_bill(conn, tenant_id, period_key, sub["plan_code"])""",
    )
    replace_exact(
        base,
        "app/jobs/settlement_job.py",
        """    for inv in open_invs:
        inv_id = inv["id"]
        conn.execute(
            "UPDATE invoices SET status = 'PENDING_SETTLE', updated_at = ? WHERE id = ?",
            (now, inv_id),
        )
        try:
            pay_invoice_from_wallet(conn, inv_id, inv["tenant_id"], idempotency_key=f"auto:{inv_id}")
            settled += 1
        except Exception as exc:
            log.error("settlement_job: error on inv=%s err=%s", inv_id, exc)
            failed += 1""",
        """    for inv in open_invs:
        inv_id = inv["id"]
        frz = conn.execute(
            "SELECT 1 FROM dispute_tickets WHERE invoice_id = ? AND status = 'OPEN' AND freeze_auto_debit = 1 LIMIT 1",
            (inv_id,),
        ).fetchone()
        if frz:
            continue
        conn.execute("SAVEPOINT sp_settle_inv")
        try:
            conn.execute("UPDATE invoices SET status = 'PENDING_SETTLE', updated_at = ? WHERE id = ?", (now, inv_id))
            pay_invoice_from_wallet(conn, inv_id, inv["tenant_id"], idempotency_key=f"auto:{inv_id}")
            conn.execute("RELEASE SAVEPOINT sp_settle_inv")
            settled += 1
        except Exception as exc:
            conn.execute("ROLLBACK TO SAVEPOINT sp_settle_inv")
            conn.execute("RELEASE SAVEPOINT sp_settle_inv")
            ex_dlq = conn.execute("SELECT id FROM settlement_dlq WHERE invoice_id = ? LIMIT 1", (inv_id,)).fetchone()
            if ex_dlq:
                conn.execute(
                    "UPDATE settlement_dlq SET error_msg = ?, status = 'PENDING', updated_at = ? WHERE id = ?",
                    (str(exc), now, ex_dlq["id"]),
                )
            else:
                conn.execute(
                    "INSERT INTO settlement_dlq (invoice_id, tenant_id, error_msg, retry_count, status, created_at, updated_at) "
                    "VALUES (?, ?, ?, 0, 'PENDING', ?, ?)",
                    (inv_id, inv["tenant_id"], str(exc), now, now),
                )
            log.error("settlement_job: error on inv=%s err=%s", inv_id, exc)
            failed += 1""",
    )
    replace_exact(
        base,
        "app/services/billing_service.py",
        """    new_status = "REJECTED" if dec == "REJECT_DISPUTE" else "UPHELD"
    conn.execute(
        "UPDATE dispute_tickets SET status = ?, resolved_at = ? WHERE id = ?",
        (new_status, now, dispute_id),
    )""",
        """    new_status = "REJECTED" if dec == "REJECT_DISPUTE" else "UPHELD"
    new_freeze = 0 if dec == "REJECT_DISPUTE" else int(row["freeze_auto_debit"])
    conn.execute(
        "UPDATE dispute_tickets SET status = ?, freeze_auto_debit = ?, resolved_at = ? WHERE id = ?",
        (new_status, new_freeze, now, dispute_id),
    )
    if dec == "REJECT_DISPUTE":
        conn.execute("UPDATE invoices SET dispute_reason = '', updated_at = ? WHERE id = ?", (now, row["invoice_id"]))""",
    )
    replace_exact(
        base,
        "app/jobs/dlq_retry_job.py",
        "    charge_cents = int(inv[\"total_cents\"])",
        "    charge_cents = max(0, int(inv[\"total_cents\"]) - int(inv[\"paid_cents\"]))",
    )
    replace_exact(
        base,
        "app/jobs/dlq_retry_job.py",
        "\"UPDATE settlement_dlq SET retry_count = retry_count + 1, updated_at = ? WHERE id = ?\"",
        "\"UPDATE settlement_dlq SET status = 'RESOLVED', retry_count = retry_count + 1, updated_at = ? WHERE id = ?\"",
    )
    replace_exact(
        base,
        "app/utils/csv_parser.py",
        """    replacements = [
        ("股份有限公司", ""),""",
        """    replacements = [
        ("（", "("),
        ("）", ")"),
        ("股份有限公司", ""),""",
    )
    replace_exact(
        base,
        "app/services/bank_statement_matcher.py",
        """    row = conn.execute("SELECT * FROM bank_statement_imports WHERE id = ?", (import_id,)).fetchone()
    if not row:
        raise LookupError("银行水单记录不存在")""",
        """    row = conn.execute("SELECT * FROM bank_statement_imports WHERE id = ?", (import_id,)).fetchone()
    if not row:
        raise LookupError("银行水单记录不存在")
    if row["status"] in ("AUTO_CLAIMED", "CLAIMED"):
        raise ValueError("该银行水单已认领入账，禁止二次重复认领")""",
    )


def apply_d3_treasury_fx(base: Path) -> None:
    # BUG-19..24
    replace_exact(
        base,
        "app/treasury/fx_settlement_service.py",
        """    today_date = utc_now_iso()[:10]
    rate_row = conn.execute(
        "SELECT rate_bps FROM fx_rates WHERE currency_code = ? AND effective_date = ? LIMIT 1",
        (ccy, today_date),
    ).fetchone()
    applied_rate_bps = int(rate_row["rate_bps"]) if rate_row else 70000

    settled_cny_cents = minor_units * (applied_rate_bps // 10000)""",
        """    inv_date = str(inv["created_at"] or utc_now_iso())[:10]
    rate_row = conn.execute(
        "SELECT rate_bps FROM fx_rates WHERE currency_code = ? AND effective_date <= ? ORDER BY effective_date DESC LIMIT 1",
        (ccy, inv_date),
    ).fetchone()
    applied_rate_bps = int(rate_row["rate_bps"]) if rate_row else 70000

    settled_cny_cents = (minor_units * applied_rate_bps + 5000) // 10000""",
    )
    replace_exact(
        base,
        "app/treasury/fx_hedging_revaluation.py",
        """        WHERE i.period_key = ?
        ORDER BY f.invoice_id ASC""",
        """        WHERE i.period_key = ? AND i.status NOT IN ('PAID', 'VOID', 'REFUNDED')
        ORDER BY f.invoice_id ASC""",
    )
    replace_exact(
        base,
        "app/treasury/fx_hedging_revaluation.py",
        "        fx_delta = booked_cny - closing_cny",
        "        fx_delta = closing_cny - booked_cny",
    )
    replace_exact(
        base,
        "app/billing_ext/tax_withholding_crossborder.py",
        """    wht_bps = int(spec["treaty_royalty_wht_bps"] if has_tax_residency_cert else spec["standard_wht_bps"])
    amt = max(0, int(invoice_net_cents))

    if not contract_gross_up_clause:
        withheld = (amt * wht_bps) // 10000
        cash_remitted = amt - withheld
        billed_gross = amt
    else:
        denom = max(1, 10000 + wht_bps)""",
        """    if not is_royalty_license:
        wht_bps = 0
    else:
        wht_bps = int(spec["treaty_royalty_wht_bps"] if has_tax_residency_cert else spec["standard_wht_bps"])
    amt = max(0, int(invoice_net_cents))

    if not contract_gross_up_clause:
        withheld = (amt * wht_bps) // 10000
        cash_remitted = amt - withheld
        billed_gross = amt
    else:
        denom = max(1, 10000 - wht_bps)""",
    )
    replace_exact(
        base,
        "app/treasury/payment_channel_router.py",
        """    if amt == 0:
        return 2""",
        """    if amt <= 0:
        return 0""",
    )
    replace_exact(
        base,
        "app/treasury/escrow_deposit_manager.py",
        """    conn.execute(
        "UPDATE escrow_accounts SET balance_cents = ?, updated_at = ? WHERE tenant_id = ?",
        (new_escrow_bal, now, tenant_id),
    )""",
        """    conn.execute(
        "UPDATE escrow_accounts SET balance_cents = ?, updated_at = ? WHERE tenant_id = ?",
        (new_escrow_bal, now, tenant_id),
    )
    new_paid = int(inv["paid_cents"]) + req_amt
    new_status = "PAID" if new_paid >= int(inv["total_cents"]) else inv["status"]
    conn.execute(
        "UPDATE invoices SET paid_cents = ?, status = ?, updated_at = ? WHERE id = ?",
        (new_paid, new_status, now, invoice_id),
    )
    conn.execute(
        "INSERT INTO invoice_payments (id, invoice_id, tenant_id, idempotency_key, cash_paid_cents, promo_paid_cents, total_paid_cents, created_at) "
        "VALUES (?, ?, ?, ?, ?, 0, ?, ?)",
        (new_id("pay_esc"), invoice_id, tenant_id, f"escrow:{invoice_id}:{now}:{req_amt}", req_amt, req_amt, now),
    )""",
    )
    replace_exact(
        base,
        "app/billing_ext/multi_entity_intercompany.py",
        """        SELECT i.*, t.tax_profile_code
        FROM invoices i
        JOIN tenants t ON t.id = i.tenant_id
        WHERE i.period_key = ? AND i.status != 'VOID'""",
        """        SELECT i.*, t.tax_profile_code, t.billing_metadata
        FROM invoices i
        JOIN tenants t ON t.id = i.tenant_id
        WHERE i.period_key = ? AND i.status != 'VOID'""",
    )
    replace_exact(
        base,
        "app/billing_ext/multi_entity_intercompany.py",
        """    for r in rows:
        d = dict(r)""",
        """    import json
    for r in rows:
        d = dict(r)
        try:
            meta = json.loads(d.get("billing_metadata") or "{}")
        except Exception:
            meta = {}
        if meta.get("intercompany") or meta.get("internal_settlement"):
            continue""",
    )


def apply_d4_fapiao_reconcile(base: Path) -> None:
    # BUG-25..31 (含下线违规热补丁)
    replace_exact(
        base,
        "app/hotfixes/__init__.py",
        """    apply_sept_close_memo_patch()
    apply_oct31_high_value_vat_patch()
    apply_nov05_fapiao_micro_split_patch()
    apply_nov_header_compat_patch()""",
        """    apply_sept_close_memo_patch()
    apply_nov_header_compat_patch()""",
    )
    replace_exact(
        base,
        "app/routes/fapiao.py",
        """    try:
        with tx_context(db_path) as conn:
            res = request_vat_fapiao_for_invoice(""",
        """    try:
        with tx_context(db_path, immediate=True) as conn:
            res = request_vat_fapiao_for_invoice(""",
    )
    replace_exact(
        base,
        "app/services/fapiao_service.py",
        "from app.vendor_blackbox.fin_rounding_engine import split_inclusive_vat_legacy",
        "from app.vendor_blackbox.fin_rounding_engine import split_inclusive_vat_exact",
    )
    replace_exact(
        base,
        "app/services/fapiao_service.py",
        """    pay_row = conn.execute(
        "SELECT COALESCE(SUM(cash_paid_cents), 0) AS cash_paid FROM invoice_payments WHERE invoice_id = ?",
        (invoice_id,),
    ).fetchone()
    cash_paid = int(pay_row["cash_paid"] or 0) if pay_row else parse_legacy_amount_cents(dict(inv), "paid_cents")
    net_cash_invoiceable = max(0, cash_paid - int(inv["refunded_cents"] or 0))
    if net_cash_invoiceable <= 0:
        raise ValueError("该账单全部由赠送金抵扣或已全额退费，可开票现金实付金额为 0")

    rate_bps = int(tax_profile["rate_bps"])
    if rate_bps > 0:
        net_cents, tax_cents = split_inclusive_vat_legacy(net_cash_invoiceable, rate_bps)""",
        """    pay_row = conn.execute(
        "SELECT COUNT(*) AS cnt, COALESCE(SUM(cash_paid_cents), 0) AS cash_paid FROM invoice_payments WHERE invoice_id = ?",
        (invoice_id,),
    ).fetchone()
    cash_paid = int(pay_row["cash_paid"] or 0) if (pay_row and int(pay_row["cnt"]) > 0) else parse_legacy_amount_cents(dict(inv), "paid_cents")
    ref_led = conn.execute(
        "SELECT COUNT(*) AS cnt, COALESCE(SUM(cash_delta_cents), 0) AS cash_ref FROM wallet_ledger WHERE ref_id = ? AND entry_type = 'REFUND'",
        (invoice_id,),
    ).fetchone()
    cash_refunded = max(0, int(ref_led["cash_ref"] or 0)) if (ref_led and int(ref_led["cnt"]) > 0) else int(inv["refunded_cents"] or 0)
    net_cash_invoiceable = max(0, cash_paid - cash_refunded)
    if net_cash_invoiceable <= 0:
        raise ValueError("该账单全部由赠送金抵扣或已全额退费，可开票现金实付金额为 0")

    rate_bps = int(tax_profile["rate_bps"])
    if rate_bps > 0:
        net_cents, tax_cents = split_inclusive_vat_exact(net_cash_invoiceable, rate_bps)""",
    )
    replace_exact(
        base,
        "app/services/fapiao_service.py",
        """    gross = parse_legacy_amount_cents(dict(inv), "total_cents")
    limit = max(10_000, int(FAPIAO_SINGLE_SHEET_MAX_CENTS))
    sheet_cnt = max(1, int(math.ceil(gross / float(limit)))) if gross > 0 else 0
    sheets: List[Dict[str, Any]] = []
    rem = gross
    for idx in range(1, sheet_cnt + 1):
        sh_gross = min(limit, rem) if idx < sheet_cnt else rem
        sh_net, sh_tax = split_inclusive_vat_legacy(sh_gross, rate_bps)
        rem -= sh_gross""",
        """    pay_row = conn.execute(
        "SELECT COUNT(*) AS cnt, COALESCE(SUM(cash_paid_cents), 0) AS cash_paid, COALESCE(SUM(promo_paid_cents), 0) AS promo_paid FROM invoice_payments WHERE invoice_id = ?",
        (invoice_id,),
    ).fetchone()
    if pay_row and int(pay_row["cnt"]) > 0:
        base_cash = int(pay_row["cash_paid"] or 0)
    else:
        base_cash = parse_legacy_amount_cents(dict(inv), "total_cents")
    ref_led = conn.execute(
        "SELECT COUNT(*) AS cnt, COALESCE(SUM(cash_delta_cents), 0) AS cash_ref FROM wallet_ledger WHERE ref_id = ? AND entry_type = 'REFUND'",
        (invoice_id,),
    ).fetchone()
    cash_ref = max(0, int(ref_led["cash_ref"] or 0)) if (ref_led and int(ref_led["cnt"]) > 0) else int(inv["refunded_cents"] or 0)
    gross = max(0, base_cash - cash_ref)
    limit = max(10_000, int(FAPIAO_SINGLE_SHEET_MAX_CENTS))
    sheet_cnt = max(1, int(math.ceil(gross / float(limit)))) if gross > 0 else 0
    total_net, total_tax = split_inclusive_vat_exact(gross, rate_bps) if rate_bps > 0 else (gross, 0)
    sheets: List[Dict[str, Any]] = []
    rem = gross
    alloc_net = 0
    alloc_tax = 0
    for idx in range(1, sheet_cnt + 1):
        sh_gross = min(limit, rem) if idx < sheet_cnt else rem
        if idx < sheet_cnt:
            sh_net, sh_tax = split_inclusive_vat_exact(sh_gross, rate_bps) if rate_bps > 0 else (sh_gross, 0)
            alloc_net += sh_net
            alloc_tax += sh_tax
        else:
            sh_net = total_net - alloc_net
            sh_tax = total_tax - alloc_tax
        rem -= sh_gross""",
    )
    replace_exact(
        base,
        "app/services/fapiao_service.py",
        """    resp = query_tax_bureau_issued_page(conn, period_key=period_key, cursor=0, page_size=500)
    records = [r for r in resp["records"] if r["status"] != "RED_ISSUED"]""",
        """    all_rows: List[Dict[str, Any]] = []
    cur = 0
    while True:
        resp = query_tax_bureau_issued_page(conn, period_key=period_key, cursor=cur, page_size=50)
        all_rows.extend(resp["records"])
        if not resp.get("has_more") or resp.get("next_cursor") is None:
            break
        cur = int(resp["next_cursor"])
    records = [r for r in all_rows if r["status"] == "ISSUED"]""",
    )
    replace_exact(
        base,
        "app/finance_recon_hub/golden_tax_red_letter_matcher.py",
        """        if not orig:
            skipped += 1
            continue
        red_id = str(item.get("red_fapiao_id") or f"FP-RED-{uuid.uuid4().hex[:6].upper()}")
        # 登记红字确认回执记录（按原票面绝对值归档备查）
        red_record = {
            "id": red_id,
            "tenant_id": orig["tenant_id"],
            "invoice_id": orig["invoice_id"],
            "fapiao_type": orig["fapiao_type"],
            "buyer_tax_id": orig["buyer_tax_id"],
            "title": orig["title"],
            "net_amount_cents": abs(int(orig["net_amount_cents"])),
            "tax_amount_cents": abs(int(orig["tax_amount_cents"])),
            "gross_amount_cents": abs(int(orig["gross_amount_cents"])),
            "sheet_count": 1,
            "status": "RED_ISSUED",
            "red_letter_of": orig_id,
            "created_at": now,
        }
        insert_fapiao_request(conn, red_record)""",
        """        if not orig or orig["status"] != "ISSUED":
            skipped += 1
            continue
        red_id = str(item.get("red_fapiao_id") or f"FP-RED-{uuid.uuid4().hex[:6].upper()}")
        red_record = {
            "id": red_id,
            "tenant_id": orig["tenant_id"],
            "invoice_id": orig["invoice_id"],
            "fapiao_type": orig["fapiao_type"],
            "buyer_tax_id": orig["buyer_tax_id"],
            "title": orig["title"],
            "net_amount_cents": -abs(int(orig["net_amount_cents"])),
            "tax_amount_cents": -abs(int(orig["tax_amount_cents"])),
            "gross_amount_cents": -abs(int(orig["gross_amount_cents"])),
            "sheet_count": 1,
            "status": "RED_ISSUED",
            "red_letter_of": orig_id,
            "created_at": now,
        }
        insert_fapiao_request(conn, red_record)
        conn.execute("UPDATE fapiao_requests SET status = 'RED_REVERSED' WHERE id = ?", (orig_id,))""",
    )
    replace_exact(
        base,
        "app/domain/reconcile.py",
        """    bill = calculate_cycle_bill(conn, inv["tenant_id"], inv["period_key"], inv["plan_code"])
    new_total = bill["total_cents"] + int(inv["late_fee_cents"])
    now = _now_iso()

    conn.execute(
        \"\"\"
        UPDATE invoices
        SET base_fee_cents = ?, overage_fee_cents = ?, tax_cents = ?, total_cents = ?, updated_at = ?
        WHERE id = ?
        \"\"\",
        (bill["base_fee_cents"], bill["overage_fee_cents"], bill["tax_cents"], new_total, now, invoice_id),
    )""",
        """    bill = calculate_cycle_bill(conn, inv["tenant_id"], inv["period_key"], inv["plan_code"])
    new_total = bill["total_cents"] + int(inv["late_fee_cents"])
    now = _now_iso()

    if get_period_status(conn, inv["period_key"]) == "CLOSED":
        old_total = parse_legacy_amount_cents(dict(inv), "total_cents")
        delta = new_total - old_total
        open_row = conn.execute(
            "SELECT period_key FROM accounting_periods WHERE status = 'OPEN' ORDER BY period_key DESC LIMIT 1"
        ).fetchone()
        open_pk = open_row["period_key"] if open_row else "2026-11"
        adj_type = "CREDIT_MEMO" if delta <= 0 else "DEBIT_MEMO"
        adj_id = f"adj_recalc_{invoice_id}"
        conn.execute(
            "INSERT OR REPLACE INTO billing_adjustments (id, tenant_id, ref_invoice_id, target_period_key, applied_period_key, adjustment_type, delta_cents, reason, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)",
            (adj_id, inv["tenant_id"], invoice_id, inv["period_key"], open_pk, adj_type, delta, f"已封账账期 {inv['period_key']} 重算跨期差额调整", now),
        )
        return {
            "invoice_id": invoice_id,
            "period_key": inv["period_key"],
            "mode": "CROSS_PERIOD_ADJUSTMENT",
            "adjustment_id": adj_id,
            "delta_cents": delta,
            "applied_period_key": open_pk,
        }

    conn.execute(
        \"\"\"
        UPDATE invoices
        SET base_fee_cents = ?, overage_fee_cents = ?, tax_cents = ?, total_cents = ?, updated_at = ?
        WHERE id = ?
        \"\"\",
        (bill["base_fee_cents"], bill["overage_fee_cents"], bill["tax_cents"], new_total, now, invoice_id),
    )""",
    )
    replace_exact(
        base,
        "app/domain/reconcile.py",
        """    if adj["status"] == "VOID":
        raise ValueError("该调账单已作废")""",
        """    if adj["status"] != "PENDING":
        raise ValueError(f"仅允许核销 PENDING 状态的调账单，当前为 {adj['status']}")
    if abs(int(adj["delta_cents"])) >= 500_000:
        apv = conn.execute("SELECT * FROM approval_tickets WHERE id = ?", (approval_ticket_id or "",)).fetchone()
        if not apv or apv["status"] != "APPROVED" or apv["tenant_id"] != adj["tenant_id"]:
            raise PermissionError("单笔满 5,000 元的调账核销必须附带已双签终审通过（APPROVED）的财务审批单")""",
    )
    replace_exact(
        base,
        "app/domain/reconcile.py",
        """    new_total = max(0, int(inv["total_cents"]) - int(adj["delta_cents"]))
    conn.execute(
        "UPDATE invoices SET total_cents = ?, updated_at = ? WHERE id = ?",
        (new_total, now, target_invoice_id),
    )
    conn.execute(
        "UPDATE billing_adjustments SET applied_period_key = ? WHERE id = ?",
        (inv["period_key"], adjustment_id),
    )""",
        """    new_total = max(0, int(inv["total_cents"]) + int(adj["delta_cents"]))
    conn.execute(
        "UPDATE invoices SET total_cents = ?, updated_at = ? WHERE id = ?",
        (new_total, now, target_invoice_id),
    )
    conn.execute(
        "UPDATE billing_adjustments SET status = 'APPLIED', applied_period_key = ? WHERE id = ?",
        (inv["period_key"], adjustment_id),
    )""",
    )
    replace_exact(
        base,
        "app/jobs/metering_flush_job.py",
        """    for ev in events:
        tenant_id = ev["tenant_id"]
        period_key = ev["period_key"]
        qty = int(ev["quantity"])""",
        """    open_row = conn.execute("SELECT period_key FROM accounting_periods WHERE status = 'OPEN' ORDER BY period_key DESC LIMIT 1").fetchone()
    active_open_pk = open_row["period_key"] if open_row else "2026-11"
    closed_pks = {r["period_key"] for r in conn.execute("SELECT period_key FROM accounting_periods WHERE status = 'CLOSED'").fetchall()}

    for ev in events:
        tenant_id = ev["tenant_id"]
        period_key = active_open_pk if ev["period_key"] in closed_pks else ev["period_key"]
        qty = int(ev["quantity"])""",
    )
