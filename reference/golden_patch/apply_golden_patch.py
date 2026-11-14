#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""黄金标准最小外科手术补丁 + 180租户脏账审计订正脚本（仅驻留主控私有参考目录）。"""
from pathlib import Path
import sqlite3
import sys


def _replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise AssertionError(f"Target snippet not found in {path}:\n{old[:180]}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def apply_patch(sandbox_dir: Path) -> None:
    # ------------------------------------------------------------------
    # 1. BUG-01: 跨层事件钩子主题对齐 + 双写兼容层快照保留 + 刷盘与出账分段核算
    # ------------------------------------------------------------------
    _replace_once(
        sandbox_dir / "app" / "hooks" / "cache_invalidators.py",
        'def register_cache_invalidation_hooks() -> None:\n'
        '    event_bus.subscribe("plan.updated", on_legacy_plan_updated_event)',
        'def register_cache_invalidation_hooks() -> None:\n'
        '    event_bus.subscribe("plan.updated", on_legacy_plan_updated_event)\n'
        '    event_bus.subscribe("subscription.plan_changed", on_legacy_plan_updated_event)',
    )

    _replace_once(
        sandbox_dir / "app" / "services" / "metering_service.py",
        '    try:\n'
        '        quantity = int(raw_quantity)\n'
        '    except (TypeError, ValueError):\n'
        '        raise ValueError("quantity 必须为整数")',
        '    try:\n'
        '        quantity = int(raw_quantity)\n'
        '    except (TypeError, ValueError):\n'
        '        raise ValueError("quantity 必须为整数")\n'
        '    if quantity <= 0:\n'
        '        raise ValueError("quantity 必须为正整数")',
    )

    _replace_once(
        sandbox_dir / "app" / "compat" / "usage_dual_write_shim.py",
        '        plan_code_at_event=None,',
        '        plan_code_at_event=resolved_plan_code,',
    )

    _replace_once(
        sandbox_dir / "app" / "compat" / "v1_v2_bridge.py",
        'def resolve_flush_plan_code(conn: sqlite3.Connection, event_row: sqlite3.Row) -> str:\n'
        '    """刷盘时解析计量事件应归入的套餐分段代码。"""\n'
        '    tenant_id = event_row["tenant_id"]',
        'def resolve_flush_plan_code(conn: sqlite3.Connection, event_row: sqlite3.Row) -> str:\n'
        '    """刷盘时解析计量事件应归入的套餐分段代码。"""\n'
        '    if event_row["plan_code_at_event"]:\n'
        '        return str(event_row["plan_code_at_event"])\n'
        '    tenant_id = event_row["tenant_id"]',
    )

    _replace_once(
        sandbox_dir / "app" / "jobs" / "metering_flush_job.py",
        '        plan_code = resolve_flush_plan_code(conn, ev)',
        '        p_row = conn.execute("SELECT status FROM accounting_periods WHERE period_key = ?", (period_key,)).fetchone()\n'
        '        if p_row and p_row["status"] == "CLOSED":\n'
        '            open_p = conn.execute("SELECT period_key FROM accounting_periods WHERE status = \'OPEN\' ORDER BY period_key DESC LIMIT 1").fetchone()\n'
        '            period_key = open_p["period_key"] if open_p else datetime.now(timezone.utc).strftime("%Y-%m")\n'
        '        plan_code = resolve_flush_plan_code(conn, ev)',
    )

    _replace_once(
        sandbox_dir / "app" / "domain" / "pricing.py",
        'def _compute_v2_merged_overage(breakdown: List[Dict[str, Any]], current_plan_code: str) -> int:\n'
        '    """v2 默认超额汇聚逻辑：将账期内各行用量累加为单一总量后套用期末当前套餐阶梯。"""\n'
        '    total_usage = sum(int(r["total_quantity"]) for r in breakdown)\n'
        '    plan = PLANS[current_plan_code]\n'
        '    return compute_tiered_overage_cents(\n'
        '        total_usage,\n'
        '        int(plan["included_quota"]),\n'
        '        plan["overage_tiers"],\n'
        '    )',
        'def _compute_v2_merged_overage(breakdown: List[Dict[str, Any]], current_plan_code: str) -> int:\n'
        '    """v2 分段超额汇聚逻辑：按账期内各套餐分段独立套用对应配额与累进阶梯。"""\n'
        '    fallback_plan = PLANS[current_plan_code]\n'
        '    raw_overage = 0\n'
        '    for seg in breakdown:\n'
        '        seg_plan = PLANS.get(seg["plan_code"], fallback_plan)\n'
        '        raw_overage += compute_tiered_overage_cents(\n'
        '            int(seg["total_quantity"]),\n'
        '            int(seg_plan["included_quota"]),\n'
        '            seg_plan["overage_tiers"],\n'
        '        )\n'
        '    return raw_overage',
    )

    # ------------------------------------------------------------------
    # 2. BUG-02 & BUG-03 & BUG-12a: 双资金池退款守恒 + 过期幂等 + 并发锁 + 预览无写副作用
    # ------------------------------------------------------------------
    _replace_once(
        sandbox_dir / "app" / "compat" / "wallet_bridge.py",
        '    legacy_fast_cash_mode: bool = True,',
        '    legacy_fast_cash_mode: bool = False,',
    )
    _replace_once(
        sandbox_dir / "app" / "compat" / "wallet_bridge.py",
        '    # 标记券批次试算占用状态供前端提示\n'
        '    if promo_est > 0:\n'
        '        conn.execute(\n'
        '            "UPDATE promo_grants SET status = \'LOCKED_PREVIEW\' WHERE tenant_id = ? AND status = \'ACTIVE\'",\n'
        '            (tenant_id,),\n'
        '        )\n\n',
        '',
    )

    _replace_once(
        sandbox_dir / "app" / "domain" / "ledger.py",
        '    if inv["status"] not in ("OPEN", "PENDING_SETTLE"):\n'
        '        raise ValueError(f"当前账单状态不允许支付: {inv[\'status\']}")',
        '    if idempotency_key:\n'
        '        dup = conn.execute(\n'
        '            "SELECT * FROM invoice_payments WHERE invoice_id = ? AND idempotency_key = ?",\n'
        '            (invoice_id, idempotency_key),\n'
        '        ).fetchone()\n'
        '        if dup:\n'
        '            return {\n'
        '                "payment_id": dup["id"],\n'
        '                "invoice_id": invoice_id,\n'
        '                "cash_paid_cents": dup["cash_paid_cents"],\n'
        '                "promo_paid_cents": dup["promo_paid_cents"],\n'
        '                "total_paid_cents": dup["total_paid_cents"],\n'
        '                "status": "PAID",\n'
        '            }\n'
        '    if inv["status"] not in ("OPEN", "PENDING_SETTLE"):\n'
        '        raise ValueError(f"当前账单状态不允许支付: {inv[\'status\']}")\n'
        '    claim = conn.execute(\n'
        '        "UPDATE invoices SET status = \'PENDING_SETTLE\' WHERE id = ? AND status IN (\'OPEN\', \'PENDING_SETTLE\') AND paid_cents < total_cents",\n'
        '        (invoice_id,),\n'
        '    )\n'
        '    if claim.rowcount != 1:\n'
        '        raise ValueError("账单已被并发结清")',
    )

    _replace_once(
        sandbox_dir / "app" / "domain" / "ledger.py",
        '    append_wallet_ledger(conn, tenant_id, "REFUND", cash_back, promo_back, invoice_id, reason, now)',
        '    if promo_back > 0:\n'
        '        conn.execute(\n'
        '            "UPDATE promo_grants SET remaining_cents = MIN(initial_cents, remaining_cents + ?), status = \'ACTIVE\' WHERE id = (SELECT id FROM promo_grants WHERE tenant_id = ? AND status IN (\'ACTIVE\', \'EXHAUSTED\') ORDER BY expires_at DESC LIMIT 1)",\n'
        '            (promo_back, tenant_id),\n'
        '        )\n'
        '    append_wallet_ledger(conn, tenant_id, "REFUND", cash_back, promo_back, invoice_id, reason, now)',
    )

    _replace_once(
        sandbox_dir / "app" / "domain" / "ledger.py",
        '    cutoff = as_of_iso or _now_iso()\n'
        '    rows = conn.execute(\n'
        '        "SELECT * FROM promo_grants WHERE expires_at <= ?",\n'
        '        (cutoff,),\n'
        '    ).fetchall()\n'
        '    expired_count = 0\n'
        '    total_deducted = 0\n'
        '    for g in rows:\n'
        '        deduct = int(g["initial_cents"])',
        '    cutoff = as_of_iso or _now_iso()\n'
        '    rows = conn.execute(\n'
        '        "SELECT * FROM promo_grants WHERE status = \'ACTIVE\' AND remaining_cents > 0 AND expires_at <= ?",\n'
        '        (cutoff,),\n'
        '    ).fetchall()\n'
        '    expired_count = 0\n'
        '    total_deducted = 0\n'
        '    for g in rows:\n'
        '        w = get_wallet(conn, g["tenant_id"])\n'
        '        deduct = min(int(g["remaining_cents"]), max(0, int(w["promo_balance_cents"])))',
    )

    # ------------------------------------------------------------------
    # 3. BUG-03 (周期防重) & BUG-04 (失败回退与死信) & BUG-11 (争议冻结 + DLQ差额扣款)
    # ------------------------------------------------------------------
    _replace_once(
        sandbox_dir / "app" / "routes" / "billing.py",
        '    try:\n'
        '        with tx_context(db_path) as conn:\n'
        '            res = facade_pay_invoice(conn, g.tenant["id"], invoice_id, idempotency_key=idem_key)',
        '    try:\n'
        '        with tx_context(db_path, immediate=True) as conn:\n'
        '            res = facade_pay_invoice(conn, g.tenant["id"], invoice_id, idempotency_key=idem_key)',
    )

    _replace_once(
        sandbox_dir / "app" / "services" / "subscription_service.py",
        '    now = _now_iso()\n'
        '    period_key = sub["cycle_end"][:7]\n'
        '    bill = calculate_cycle_bill(conn, tenant_id, period_key, sub["plan_code"])',
        '    now = _now_iso()\n'
        '    existing = conn.execute(\n'
        '        "SELECT id, total_cents, period_key FROM invoices WHERE tenant_id = ? AND cycle_start = ? AND cycle_end = ? AND status != \'VOID\'",\n'
        '        (tenant_id, sub["cycle_start"], sub["cycle_end"]),\n'
        '    ).fetchone()\n'
        '    if existing:\n'
        '        return {"invoice_id": existing["id"], "total_cents": existing["total_cents"], "period_key": existing["period_key"]}\n'
        '    period_key = sub["cycle_end"][:7]\n'
        '    bill = calculate_cycle_bill(conn, tenant_id, period_key, sub["plan_code"])',
    )

    _replace_once(
        sandbox_dir / "app" / "jobs" / "settlement_job.py",
        '    for sub in subs:\n'
        '        tenant_id = sub["tenant_id"]',
        '    for sub in subs:\n'
        '        tenant_id = sub["tenant_id"]\n'
        '        exists = conn.execute(\n'
        '            "SELECT id FROM invoices WHERE tenant_id = ? AND cycle_start = ? AND cycle_end = ? AND status != \'VOID\'",\n'
        '            (tenant_id, sub["cycle_start"], sub["cycle_end"]),\n'
        '        ).fetchone()\n'
        '        if exists:\n'
        '            continue',
    )

    _replace_once(
        sandbox_dir / "app" / "jobs" / "settlement_job.py",
        '    for inv in open_invs:\n'
        '        inv_id = inv["id"]\n'
        '        conn.execute(\n'
        '            "UPDATE invoices SET status = \'PENDING_SETTLE\', updated_at = ? WHERE id = ?",\n'
        '            (now, inv_id),\n'
        '        )',
        '    for inv in open_invs:\n'
        '        inv_id = inv["id"]\n'
        '        if (inv["dispute_reason"] or "").strip():\n'
        '            continue\n'
        '        dsp = conn.execute(\n'
        '            "SELECT 1 FROM dispute_tickets WHERE invoice_id = ? AND status = \'OPEN\' AND freeze_auto_debit = 1",\n'
        '            (inv_id,),\n'
        '        ).fetchone()\n'
        '        if dsp:\n'
        '            continue\n'
        '        conn.execute(\n'
        '            "UPDATE invoices SET status = \'PENDING_SETTLE\', updated_at = ? WHERE id = ?",\n'
        '            (now, inv_id),\n'
        '        )',
    )

    _replace_once(
        sandbox_dir / "app" / "jobs" / "settlement_job.py",
        '        except Exception as exc:\n'
        '            log.error("settlement_job: error on inv=%s err=%s", inv_id, exc)\n'
        '            failed += 1',
        '        except Exception as exc:\n'
        '            log.warning("settlement_job: reverting inv=%s to OPEN due to %s", inv_id, exc)\n'
        '            conn.execute("UPDATE invoices SET status = \'OPEN\', updated_at = ? WHERE id = ?", (now, inv_id))\n'
        '            conn.execute(\n'
        '                "INSERT INTO settlement_dlq (invoice_id, tenant_id, error_msg, retry_count, status, created_at, updated_at) VALUES (?, ?, ?, 1, \'PENDING\', ?, ?)",\n'
        '                (inv_id, inv["tenant_id"], str(exc), now, now),\n'
        '            )\n'
        '            failed += 1',
    )

    _replace_once(
        sandbox_dir / "app" / "jobs" / "dlq_retry_job.py",
        '    # 直接按账单票面总额扣款\n'
        '    charge_cents = int(inv["total_cents"])',
        '    # 仅补扣扣除历史已付后的剩余未付差额\n'
        '    charge_cents = int(inv["total_cents"]) - int(inv["paid_cents"])',
    )

    # ------------------------------------------------------------------
    # 4. BUG-05: 复合条件 IDOR / 管理端鉴权 / 规范化路径边界 / 堆栈脱敏 / 前端 XSS 转义
    # ------------------------------------------------------------------
    _replace_once(
        sandbox_dir / "app" / "services" / "billing_service.py",
        '    # 门户与坐席通道租户访问守卫\n'
        '    if inv["tenant_id"] != requester_tenant_id and audit_channel == "STRICT_TENANT_ENFORCE":\n'
        '        raise PermissionError("无权访问其他租户账单")',
        '    # 门户与坐席通道租户访问守卫\n'
        '    if inv["tenant_id"] != requester_tenant_id:\n'
        '        raise PermissionError("无权访问其他租户账单")',
    )
    _replace_once(
        sandbox_dir / "app" / "services" / "billing_service.py",
        '    if inv["status"] == "VOID":\n'
        '        raise ValueError("已作废账单不支持发起争议")\n'
        '    elif inv["currency_unit"] == "LEGACY_INTERNAL_V0":\n'
        '        if inv["tenant_id"] != requester_tenant_id:\n'
        '            raise PermissionError("无权操作其他租户账单")',
        '    if inv["tenant_id"] != requester_tenant_id:\n'
        '        raise PermissionError("无权操作其他租户账单")\n'
        '    if inv["status"] == "VOID":\n'
        '        raise ValueError("已作废账单不支持发起争议")',
    )

    _replace_once(
        sandbox_dir / "app" / "infra" / "security.py",
        'def resolve_export_filepath(export_root: str, requested_file: str) -> str:\n'
        '    """解析对账导出文件路径。"""\n'
        '    os.makedirs(export_root, exist_ok=True)\n'
        '    cleaned = requested_file.replace("../", "")\n'
        '    return os.path.join(export_root, cleaned)',
        'def resolve_export_filepath(export_root: str, requested_file: str) -> str:\n'
        '    """解析并校验对账导出文件规范化边界。"""\n'
        '    os.makedirs(export_root, exist_ok=True)\n'
        '    root_real = os.path.realpath(export_root)\n'
        '    target = os.path.realpath(os.path.join(root_real, requested_file))\n'
        '    if not (target == root_real or target.startswith(root_real + os.sep)):\n'
        '        raise PermissionError("非法文件路径")\n'
        '    if not os.path.isfile(target):\n'
        '        raise FileNotFoundError("导出文件不存在")\n'
        '    return target',
    )

    _replace_once(
        sandbox_dir / "app" / "routes" / "admin.py",
        '@bp.route("/jobs/run", methods=["POST"])\n'
        'def trigger_jobs():',
        '@bp.route("/jobs/run", methods=["POST"])\n'
        '@require_admin\n'
        'def trigger_jobs():',
    )
    _replace_once(
        sandbox_dir / "app" / "routes" / "admin.py",
        '@bp.route("/reconcile/export", methods=["GET"])\n'
        'def export_reconcile_file():',
        '@bp.route("/reconcile/export", methods=["GET"])\n'
        '@require_admin\n'
        'def export_reconcile_file():',
    )
    _replace_once(
        sandbox_dir / "app" / "routes" / "admin.py",
        '    export_root = current_app.config.get("EXPORT_DIR", EXPORT_DIR)\n'
        '    target = resolve_export_filepath(export_root, filename)\n'
        '    with open(target, "r", encoding="utf-8") as f:\n'
        '        return Response(f.read(), mimetype="text/plain; charset=utf-8")',
        '    export_root = current_app.config.get("EXPORT_DIR", EXPORT_DIR)\n'
        '    try:\n'
        '        target = resolve_export_filepath(export_root, filename)\n'
        '    except PermissionError as e:\n'
        '        return jsonify({"error": str(e)}), 403\n'
        '    except FileNotFoundError as e:\n'
        '        return jsonify({"error": str(e)}), 404\n'
        '    with open(target, "r", encoding="utf-8") as f:\n'
        '        return Response(f.read(), mimetype="text/plain; charset=utf-8")',
    )

    _replace_once(
        sandbox_dir / "app" / "infra" / "config.py",
        '    "VERBOSE_500_DIAGNOSTICS": True,',
        '    "VERBOSE_500_DIAGNOSTICS": False,',
    )
    _replace_once(
        sandbox_dir / "app" / "server.py",
        '    @app.errorhandler(Exception)\n'
        '    def handle_unexpected_error(err):\n'
        '        body = {"error": "Internal Server Error"}\n'
        '        if FEATURE_FLAGS.get("VERBOSE_500_DIAGNOSTICS", True):\n'
        '            body["error"] = str(err)\n'
        '            body["traceback"] = traceback.format_exc()\n'
        '        return jsonify(body), 500',
        '    @app.errorhandler(Exception)\n'
        '    def handle_unexpected_error(err):\n'
        '        from werkzeug.exceptions import HTTPException\n'
        '        if isinstance(err, HTTPException):\n'
        '            return err\n'
        '        return jsonify({"error": "Internal Server Error"}), 500',
    )

    _replace_once(
        sandbox_dir / "static" / "js" / "views" / "invoice_table.js",
        'import { fmtYuan } from "../fmt.js";',
        'import { escapeHtml, fmtYuan } from "../fmt.js";',
    )
    _replace_once(
        sandbox_dir / "static" / "js" / "views" / "invoice_table.js",
        '<td class="dispute-cell">${inv.dispute_reason || "-"}</td>',
        '<td class="dispute-cell">${escapeHtml(inv.dispute_reason || "-")}</td>',
    )
    _replace_once(
        sandbox_dir / "static" / "js" / "views" / "invoice_table.js",
        '<td>${l.note || "-"}</td>',
        '<td>${escapeHtml(l.note || "-")}</td>',
    )
    _replace_once(
        sandbox_dir / "static" / "js" / "views" / "tenant_grid.js",
        'import { fmtYuan } from "../fmt.js";',
        'import { escapeHtml, fmtYuan } from "../fmt.js";',
    )
    _replace_once(
        sandbox_dir / "static" / "js" / "views" / "tenant_grid.js",
        '<td class="tenant-company-cell">${t.company_name}</td>',
        '<td class="tenant-company-cell">${escapeHtml(t.company_name)}</td>',
    )

    # ------------------------------------------------------------------
    # 5. BUG-07 & BUG-15: CLOSED 已封账保护 + 跨期调账有向符号核销
    # ------------------------------------------------------------------
    _replace_once(
        sandbox_dir / "app" / "domain" / "reconcile.py",
        '    bill = calculate_cycle_bill(conn, inv["tenant_id"], inv["period_key"], inv["plan_code"])\n'
        '    new_total = bill["total_cents"] + int(inv["late_fee_cents"])\n'
        '    now = _now_iso()',
        '    bill = calculate_cycle_bill(conn, inv["tenant_id"], inv["period_key"], inv["plan_code"])\n'
        '    new_total = bill["total_cents"] + int(inv["late_fee_cents"])\n'
        '    now = _now_iso()\n'
        '    if get_period_status(conn, inv["period_key"]) == "CLOSED":\n'
        '        delta = new_total - int(inv["total_cents"])\n'
        '        adj_id = f"adj_{uuid.uuid4().hex[:10]}"\n'
        '        open_row = conn.execute("SELECT period_key FROM accounting_periods WHERE status = \'OPEN\' ORDER BY period_key DESC LIMIT 1").fetchone()\n'
        '        applied_period = open_row["period_key"] if open_row else datetime.now(timezone.utc).strftime("%Y-%m")\n'
        '        conn.execute(\n'
        '            """INSERT INTO billing_adjustments (id, tenant_id, ref_invoice_id, target_period_key, applied_period_key, adjustment_type, delta_cents, reason, status, created_at)\n'
        '               VALUES (?, ?, ?, ?, ?, \'CLOSED_PERIOD_RECALC\', ?, \'已封账期间重算差额转入当期调账\', \'PENDING\', ?)""",\n'
        '            (adj_id, inv["tenant_id"], invoice_id, inv["period_key"], applied_period, delta, now),\n'
        '        )\n'
        '        return {"invoice_id": invoice_id, "period_key": inv["period_key"], "mode": "ADJUSTMENT_CREATED", "adjustment_id": adj_id, "delta_cents": delta}',
    )
    _replace_once(
        sandbox_dir / "app" / "domain" / "reconcile.py",
        '    # 沿用早期折扣抵扣公式计算新总额\n'
        '    new_total = max(0, int(inv["total_cents"]) - int(adj["delta_cents"]))',
        '    # 按有向符号代数相加（负数冲减客户应付，正数补收）\n'
        '    new_total = max(0, int(inv["total_cents"]) + int(adj["delta_cents"]))',
    )

    # ------------------------------------------------------------------
    # 6. BUG-08 & BUG-09 & BUG-10 & BUG-12b & BUG-13 & BUG-14
    # ------------------------------------------------------------------
    # BUG-08: 撤回 10-31 遗留启动期大额价外税抹零热补丁
    _replace_once(
        sandbox_dir / "app" / "hotfixes" / "hotfix_20261031_tz_and_vip.py",
        'def apply_oct31_high_value_vat_patch() -> None:\n'
        '    global _PATCH_INSTALLED\n'
        '    if _PATCH_INSTALLED:\n'
        '        return\n'
        '    pricing_mod.compute_tax_breakdown = _hotfix_tax_wrapper\n'
        '    _PATCH_INSTALLED = True',
        'def apply_oct31_high_value_vat_patch() -> None:\n'
        '    return',
    )

    # BUG-09: 动态配置表字符串布尔值精确解析
    _replace_once(
        sandbox_dir / "app" / "infra" / "runtime_config_loader.py",
        '        if row is not None and row["config_value"] is not None:\n'
        '            # 直接转为布尔返回\n'
        '            return bool(row["config_value"])',
        '        if row is not None and row["config_value"] is not None:\n'
        '            return str(row["config_value"]).strip().lower() in ("1", "true", "yes", "on")',
    )

    # BUG-10: 边缘网关批量上报非正数拦截 + UTC 账期转换 + event_id 幂等去重
    _replace_once(
        sandbox_dir / "app" / "gateway_ingest" / "batch_ingest_service.py",
        '        if qty < 0:\n'
        '            raise ValueError("批量事件 quantity 不允许为负数")\n\n'
        '        raw_ts = str(item.get("occurred_at") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")).strip()\n'
        '        # 截取前 7 位作为归属账期\n'
        '        derived_period_key = str(item.get("period_key") or raw_ts[:7])\n'
        '        eid = str(item.get("event_id") or f"ue_b_{uuid.uuid4().hex[:12]}").strip()',
        '        if qty <= 0:\n'
        '            raise ValueError("批量事件 quantity 必须为正整数")\n\n'
        '        raw_ts = str(item.get("occurred_at") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")).strip()\n'
        '        if item.get("period_key"):\n'
        '            derived_period_key = str(item["period_key"]).strip()\n'
        '        else:\n'
        '            parsed_dt = datetime.fromisoformat(raw_ts.replace("Z", "+00:00")).astimezone(timezone.utc)\n'
        '            derived_period_key = parsed_dt.strftime("%Y-%m")\n'
        '        eid = str(item.get("event_id") or f"ue_b_{uuid.uuid4().hex[:12]}").strip()\n'
        '        dup = conn.execute(\n'
        '            "SELECT 1 FROM usage_events WHERE id = ? LIMIT 1",\n'
        '            (eid,),\n'
        '        ).fetchone()\n'
        '        if dup:\n'
        '            duplicates += 1\n'
        '            continue',
    )

    # BUG-12b: 资费缓存代理返回深拷贝防止调用端原地篡改污染缓存
    _replace_once(
        sandbox_dir / "app" / "enterprise_catalog_rules" / "tariff_strategy_chain.py",
        'from abc import ABC, abstractmethod\n'
        'from typing import Any, Dict',
        'from abc import ABC, abstractmethod\n'
        'import copy\n'
        'from typing import Any, Dict',
    )
    _replace_once(
        sandbox_dir / "app" / "enterprise_catalog_rules" / "tariff_strategy_chain.py",
        '        # 直接返回缓存中的字典对象引用\n'
        '        return self._cache[key]',
        '        return copy.deepcopy(self._cache[key])',
    )

    # BUG-13: 数电发票申请并发写锁 + 含税拆票分位守恒 + 金税四期 SDK 游标翻页全量对账
    _replace_once(
        sandbox_dir / "app" / "routes" / "fapiao.py",
        '    try:\n'
        '        with tx_context(db_path) as conn:\n'
        '            res = request_vat_fapiao_for_invoice(',
        '    try:\n'
        '        with tx_context(db_path, immediate=True) as conn:\n'
        '            res = request_vat_fapiao_for_invoice(',
    )
    _replace_once(
        sandbox_dir / "app" / "services" / "fapiao_service.py",
        'from app.vendor_blackbox.fin_rounding_engine import split_inclusive_vat_legacy',
        'from app.vendor_blackbox.fin_rounding_engine import split_inclusive_vat_exact as split_inclusive_vat_legacy',
    )
    _replace_once(
        sandbox_dir / "app" / "services" / "fapiao_service.py",
        '    # 传入 page_size=500 期望一次拉全整月发票记录\n'
        '    resp = query_tax_bureau_issued_page(conn, period_key=period_key, cursor=0, page_size=500)\n'
        '    records = resp["records"]',
        '    records = []\n'
        '    cursor = 0\n'
        '    while True:\n'
        '        resp = query_tax_bureau_issued_page(conn, period_key=period_key, cursor=cursor, page_size=500)\n'
        '        records.extend(resp["records"])\n'
        '        if not resp.get("has_more") or resp.get("next_cursor") is None:\n'
        '            break\n'
        '        cursor = int(resp["next_cursor"])',
    )

    # BUG-14: 移除每请求 event_bus 订阅泄漏 + 独立审计快照异常路径关闭 SQLite 连接
    _replace_once(
        sandbox_dir / "app" / "middleware" / "request_context.py",
        '        req_trace = g.request_id\n'
        '        event_bus.subscribe("invoice.paid", lambda p: runtime_metrics.inc(f"trace.paid.{req_trace[:0]}total"))\n',
        '',
    )
    _replace_once(
        sandbox_dir / "app" / "services" / "report_export_service.py",
        '    raw_conn = sqlite3.connect(db_path, timeout=5.0)\n'
        '    raw_conn.row_factory = sqlite3.Row\n'
        '    if not period_key or len(period_key) != 7 or period_key[4] != "-" or not period_key[:4].isdigit() or not period_key[5:].isdigit():\n'
        '        raise ValueError(f"非法账期格式: {period_key}")\n'
        '    cnt = raw_conn.execute("SELECT COUNT(*) AS c FROM invoices WHERE period_key = ?", (period_key,)).fetchone()["c"]\n'
        '    raw_conn.close()\n'
        '    return {"period_key": period_key, "invoice_count": int(cnt)}',
        '    raw_conn = sqlite3.connect(db_path, timeout=5.0)\n'
        '    try:\n'
        '        raw_conn.row_factory = sqlite3.Row\n'
        '        if not period_key or len(period_key) != 7 or period_key[4] != "-" or not period_key[:4].isdigit() or not period_key[5:].isdigit():\n'
        '            raise ValueError(f"非法账期格式: {period_key}")\n'
        '        cnt = raw_conn.execute("SELECT COUNT(*) AS c FROM invoices WHERE period_key = ?", (period_key,)).fetchone()["c"]\n'
        '        return {"period_key": period_key, "invoice_count": int(cnt)}\n'
        '    finally:\n'
        '        raw_conn.close()',
    )

    # ------------------------------------------------------------------
    # 7. A2 线上快照脏账安全订正（严守 2026-09 / 2026-10 封账红线与健康租户零误伤）
    # ------------------------------------------------------------------
    conn = sqlite3.connect(str(sandbox_dir / "data" / "yunce_billing.db"))
    try:
        # 1) 云图数据 t_cust_019: ENTERPRISE(80k) + STARTER(5k) -> overage=0, total=19900
        conn.execute("UPDATE invoices SET overage_fee_cents = 0, total_cents = 19900 WHERE id = 'INV-202611-0019'")
        # 2) 瀚海物联 t_cust_083: PRO(42k->0) + STARTER(15k->15000) -> overage=15000, total=34900
        conn.execute("UPDATE invoices SET overage_fee_cents = 15000, total_cents = 34900 WHERE id = 'INV-202611-0083'")
        # 3) 蓝海智造 t_cust_034: 已扣款 59900，状态由 PENDING_SETTLE 订正为 PAID
        conn.execute("UPDATE invoices SET status = 'PAID', paid_cents = 59900 WHERE id = 'INV-202611-0034'")
        # 4) 千帆供应链 t_cust_092: 未扣款余额不足，状态由 PENDING_SETTLE 回退为 OPEN
        conn.execute("UPDATE invoices SET status = 'OPEN', paid_cents = 0 WHERE id = 'INV-202611-0092'")
        # 5) 飞跃零售 t_cust_051: 10000 退款从现金冲回赠送金 -> cash=10000, promo=10100
        conn.execute("UPDATE wallets SET cash_balance_cents = 10000, promo_balance_cents = 10100 WHERE tenant_id = 't_cust_051'")
        conn.execute("UPDATE promo_grants SET remaining_cents = 10100 WHERE id = 'pg_cust_051'")
        # 6) 锐捷医疗 t_cust_067: 重复过期扣成 -16000 的赠送金余额订正归零
        conn.execute("UPDATE wallets SET promo_balance_cents = 0 WHERE tenant_id = 't_cust_067'")
        # 7) 星河传媒 t_cust_078: 同周期重复生成的第二张续费账单作废 VOID
        conn.execute("UPDATE invoices SET status = 'VOID' WHERE id = 'INV-202611-0978'")
        # 8) 宏途跨境物流 t_cust_118: 补齐被 10-31 热补丁抹零的 6% 大额价外税 (219900 + 13194 = 233094)
        conn.execute("UPDATE invoices SET tax_cents = 13194, total_cents = 233094 WHERE id = 'INV-202611-0118'")
        # 9) 磐石数科 t_cust_132: 冲回 DLQ 重复多扣的 20000 分现金，实付归正 59900、钱包恢复 30100
        conn.execute("UPDATE invoices SET paid_cents = 59900, status = 'PAID' WHERE id = 'INV-202611-0132'")
        conn.execute("UPDATE wallets SET cash_balance_cents = 30100 WHERE tenant_id = 't_cust_132'")
        # 10) 凌云智能 t_cust_145: 解锁被结算预览接口误锁为 LOCKED_PREVIEW 的赠送金券批次
        conn.execute("UPDATE promo_grants SET status = 'ACTIVE', remaining_cents = 15000 WHERE id = 'pg_cust_145'")
        # 11) 远航精密 t_cust_156: 修正反算贷项调账单 (19900 + (-15000) = 4900)
        conn.execute("UPDATE invoices SET total_cents = 4900 WHERE id = 'INV-202611-0156'")
        # 12) 智汇云科技 t_cust_012: 2026-09 已封账账单 INV-202609-0012 原值不动，在 2026-11 OPEN 期登记 -20000 跨期调账
        conn.execute(
            """INSERT OR IGNORE INTO billing_adjustments
               (id, tenant_id, ref_invoice_id, target_period_key, applied_period_key, adjustment_type, delta_cents, reason, status, created_at)
               VALUES ('adj_202609_0012', 't_cust_012', 'INV-202609-0012', '2026-09', '2026-11', 'CREDIT_NOTE', -20000, '9月已封账账单超额费多收200元跨期冲抵', 'PENDING', '2026-11-14T00:00:00Z')"""
        )
        conn.commit()
    finally:
        conn.close()

    # ------------------------------------------------------------------
    # 8. 新增复现与并发回归测试 (通过 C2 突变检验)
    # ------------------------------------------------------------------
    (sandbox_dir / "tests" / "test_regression_fixes.py").write_text(
        '''# -*- coding: utf-8 -*-
import os
import shutil
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.domain.pricing import calculate_cycle_bill
from app.domain.reconcile import recalculate_invoice_for_period
from app.infra.config import ADMIN_API_KEY
from app.infra.db import tx_context
from app.jobs.metering_flush_job import flush_usage_events
from app.server import create_app


class GoldenRegressionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="golden_reg_")
        self.db = os.path.join(self.tmp, "test.db")
        shutil.copy2(Path(__file__).resolve().parent.parent / "data" / "yunce_billing.db", self.db)
        self.app = create_app(db_path=self.db)
        self.client = self.app.test_client()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_event_bus_cache_invalidation_and_segmented_billing(self):
        h = {"X-Tenant-Token": "tok_cust_009"}
        self.client.get("/api/subscriptions/current?period_key=2026-11", headers=h)
        self.client.post("/api/usage/events", headers=h, json={"quantity": 40000, "period_key": "2026-11"})
        self.client.post("/api/subscriptions/change-plan", headers=h, json={"plan_code": "STARTER"})
        snap = self.client.get("/api/subscriptions/current?period_key=2026-11", headers=h).get_json()["quota"]
        self.assertEqual(snap["plan_code"], "STARTER")
        self.client.post("/api/usage/events", headers=h, json={"quantity": 12000, "period_key": "2026-11"})
        with tx_context(self.db, immediate=True) as conn:
            flush_usage_events(conn)
            bill = calculate_cycle_bill(conn, "t_cust_009", "2026-11", "STARTER")
        self.assertEqual(bill["overage_fee_cents"], 6000)

    def test_security_boundaries_and_hotfix_tax(self):
        r1 = self.client.post("/api/usage/events", headers={"X-Tenant-Token": "tok_cust_008"}, json={"quantity": -10})
        self.assertEqual(r1.status_code, 400)
        r2 = self.client.get("/api/invoices/INV-202611-0012", headers={"X-Tenant-Token": "tok_cust_008"})
        self.assertEqual(r2.status_code, 403)
        r3 = self.client.get(
            "/api/admin/reconcile/export?file=....//....//app/server.py",
            headers={"X-Admin-Key": ADMIN_API_KEY},
        )
        self.assertIn(r3.status_code, (400, 403, 404))
        with tx_context(self.db) as conn:
            bill_118 = calculate_cycle_bill(conn, "t_cust_118", "2026-11", "ENTERPRISE")
        self.assertEqual(bill_118["tax_cents"], 13194)
        self.assertEqual(bill_118["total_cents"], 233094)

    def test_batch_utc_fapiao_pagination_and_signed_adjustment(self):
        h = {"X-Tenant-Token": "tok_cust_008"}
        payload = {"events": [{"event_id": "ev_reg_utc_1", "quantity": 500, "occurred_at": "2026-12-01T01:00:00+08:00"}]}
        self.assertEqual(self.client.post("/api/usage/batch", headers=h, json=payload).status_code, 201)
        self.assertEqual(self.client.post("/api/usage/batch", headers=h, json=payload).status_code, 201)
        rec = self.client.get("/api/fapiao/reconcile/2026-10", headers={"X-Admin-Key": ADMIN_API_KEY}).get_json()
        self.assertEqual(rec["fetched_count"], 64)

    def test_concurrent_pay_and_closed_period_protection(self):
        with tx_context(self.db, immediate=True) as conn:
            conn.execute(
                """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
                   base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
                   currency_unit, status, created_at, updated_at)
                   VALUES ('INV-G-CONC', 't_cust_012', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z',
                   'PRO', 59900, 0, 0, 0, 59900, 0, 0, 'CENTS', 'OPEN', '2026-11-12T00:00:00Z', '2026-11-12T00:00:00Z')"""
            )
            conn.execute("UPDATE usage_summaries SET total_quantity = 25000 WHERE tenant_id = 't_cust_008' AND period_key = '2026-09'")
            recalculate_invoice_for_period(conn, "INV-202609-0008", actor="unit_test")

        barrier = threading.Barrier(4)
        def _pay(idx):
            barrier.wait(timeout=5)
            return self.app.test_client().post(
                "/api/invoices/INV-G-CONC/pay",
                headers={"X-Tenant-Token": "tok_cust_012", "Idempotency-Key": f"gk-{idx}"},
            ).status_code

        with ThreadPoolExecutor(max_workers=4) as ex:
            codes = list(ex.map(_pay, range(4)))
        self.assertEqual(codes.count(200), 1)

        with tx_context(self.db) as conn:
            inv09 = conn.execute("SELECT total_cents FROM invoices WHERE id = 'INV-202609-0008'").fetchone()
            self.assertEqual(inv09["total_cents"], 19900)
''',
        encoding="utf-8",
    )

    # ------------------------------------------------------------------
    # 9. 填写完整的《事故排查与处置说明.md》（逐条覆盖 F01～F38）
    # ------------------------------------------------------------------
    (sandbox_dir / "事故排查与处置说明.md").write_text(
        """# 事故排查与处置说明

## 1. 反馈清单逐条甄别（`F01`～`F38`：真实缺陷 vs 伪反馈 / 过期文档误导 / 越界需求）
- **F01 & F23（真实缺陷 -> BUG-01 + A2）**：`subscription_service` 发布 `subscription.plan_changed` 而 `hooks/cache_invalidators.py` 仅订阅 `plan.updated`；`compat/usage_dual_write_shim.py` 丢弃 `plan_code_at_event`，`compat/v1_v2_bridge.py` 刷盘拉取期末套餐且 `domain/pricing.py` 未按套餐分段独立计算超额。已修复代码并将云图数据（`INV-202611-0019`）订正为 `19900` 分、瀚海物联（`INV-202611-0083`）订正为 `34900` 分。
- **F02（真实缺陷 -> BUG-02 + A2）**：`compat/wallet_bridge.py` 默认开启 `legacy_fast_cash_mode=True` 导致赠送金抵扣被全额退成可提现现金，且 `domain/ledger.py` 未恢复券剩余额度。已修复并将飞跃零售（`t_cust_051`）订正为 `cash=10000, promo=10100`。
- **F03（真实缺陷 -> BUG-02 + A2）**：`domain/ledger.py:expire_promo_grants` 未限定 `status='ACTIVE' AND remaining_cents > 0` 且按 `initial_cents` 扣减，重复执行将钱包扣成负数。已修复并将锐捷医疗（`t_cust_067`）赠送金余额归零。
- **F04（真实缺陷 -> BUG-03）**：`routes/billing.py` 支付路由未开启 `IMMEDIATE` 写锁，`pay_invoice_from_wallet` 缺少幂等键重放与 `PENDING_SETTLE` 原子状态抢占。已补齐。
- **F05（真实缺陷 -> BUG-03 + A2）**：`jobs/settlement_job.py` 与 `services/subscription_service.py` 均缺少同周期非 `VOID` 账单防重校验。已补齐并将星河传媒重复单 `INV-202611-0978` 作废（`VOID`）。
- **F06（真实缺陷 -> BUG-04 + A2）**：`jobs/settlement_job.py` 预置 `PENDING_SETTLE` 后吞掉异常，未回退 `OPEN` 与落库 `settlement_dlq`。已修复并将蓝海智造 `INV-202611-0034` 归正 `PAID/59900`、千帆供应链 `INV-202611-0092` 回退 `OPEN/0`。
- **F07 & F08（真实缺陷 -> BUG-05）**：`services/billing_service.py` 详情与争议接口存在复合条件绕过型 IDOR；`routes/admin.py` 批处理与导出漏加 `@require_admin`；`infra/security.py` 仅做简单替换可被 `....//` 绕过；`server.py` 泄露 500 堆栈；`services/metering_service.py` 未拒绝非正数；活跃视图 `static/js/views/invoice_table.js` 与 `tenant_grid.js` 漏调 `escapeHtml`。均已修复。
- **F09（真实缺陷 -> BUG-07 + A2）**：`domain/reconcile.py` 与 `jobs/metering_flush_job.py` 未保护 `CLOSED` 封账期。已改为转入当前 `OPEN` 期或生成跨期调账单；针对智汇云科技 `INV-202609-0012` 在 `2026-11` 新增 `delta_cents=-20000` 的 `billing_adjustments` 记录，严守 `2026-09`/`2026-10` 原值不动。
- **F10（真实缺陷 -> BUG-08 + A2）**：`server.py` 启动时调用 `app/hotfixes/hotfix_20261031_tz_and_vip.py` 猴子补丁，对税前 `>= 200000` 分的 `CN_VAT_6_EXCLUSIVE` 账单强行抹零税额。已撤回该遗留热补丁，并将宏途跨境物流 `INV-202611-0118` 补齐税额 `13194` 分、总额 `233094` 分。
- **F11（真实缺陷 -> BUG-09）**：`app/infra/runtime_config_loader.py` 直接执行 `bool(row["config_value"])`，将数据库字符串 `'false'` 误判为 `True` 导致期中升级补差价全免。已改为大小写无关字符串真值解析。
- **F12 & F13（真实缺陷 -> BUG-10）**：`app/gateway_ingest/batch_ingest_service.py` 未将带时区时间戳转为 UTC 再提取 `YYYY-MM`，未拦截 `quantity <= 0`，且缺少 `event_id` 幂等去重。已全面修复。
- **F14 & F15（真实缺陷 -> BUG-11 + A2）**：`settlement_job.py` 自动扣款未跳过争议冻结账单（`dispute_reason` / `dispute_tickets`）；`dlq_retry_job.py` 内联扣款无视 `paid_cents` 直接重扣 `total_cents`。已修复并将磐石数科 `INV-202611-0132` 归正 `paid_cents=59900`、钱包现金退回至 `30100` 分。
- **F16 & F17（真实缺陷 -> BUG-12 + A2）**：`compat/wallet_bridge.py:simulate_wallet_deduction_preview` 在 `GET` 预览中违规将 `promo_grants` 改写为 `LOCKED_PREVIEW`；`tariff_strategy_chain.py` 缓存代理直接返回可变字典引用导致跨请求污染。已移除写库副作用、改为 `deepcopy` 返回，并将凌云智能 `pg_cust_145` 恢复为 `ACTIVE/15000`。
- **F18 & F19（真实缺陷 -> BUG-13）**：`chinatax_golden4_sdk` 单页硬上限 50 条而 `fapiao_service.py` 未跟随 `has_more/next_cursor` 翻页；`split_inclusive_vat_legacy` 双重向下取整导致 `19900` 分拆票少 1 分钱；`routes/fapiao.py` 申请开票未加 `IMMEDIATE` 事务锁。已全部修复。
- **F20（真实缺陷 -> BUG-14）**：`middleware/request_context.py` 在 `before_request` 中每次请求向全局 `event_bus` 注册匿名订阅造成内存泄漏；`report_export_service.py:run_standalone_period_audit_snapshot` 校验抛错时未关闭裸 `sqlite3` 连接。已移除泄漏监听并补齐 `try...finally` 关闭句柄。
- **F21（真实缺陷 -> BUG-15 + A2）**：`domain/reconcile.py:apply_adjustment_to_open_invoice` 将有向 `delta_cents` 写反为减法，导致负数贷项减免变成加收。已修正为代数相加，并将远航精密 `INV-202611-0156` 总额订正为 `4900` 分。
- **F22 & F24（工程清查与架构提醒）**：已全库核验 180 租户并将 `2026-11` 全部 11 处开放期脏账与 1 笔跨期调账修平；核清活跃链路，未误改 2024/2025 历史静态工作台与孤岛包。
- **F25～F38（伪反馈 / 过期文档陷阱 / 违规越界诉求，全部保持定力拒绝改动）**：
  - `F25`：超额累进阶梯分段计费符合权威《产品与账务规则 v2.6》，不改；
  - `F26`：期中退订不退当期基础月费、服务保留至期末符合规范，不改；
  - `F27`：15 家 `ACTIVE_LEGACY` / `YUAN_STR` 2024 存量老租户受长期合同保护（`BUG-06`），严禁删改；
  - `F28`：逾期滞纳金全平台统一 5%，无 VIP 豁免特权，拒绝；
  - `F29`：盛世跨境科技 `INV-202611-0015` 属正常 6% 价外税小额账单（`63494` 分），严禁误改；
  - `F30`：`prod_20261111.log` 显示 `customer-025` 首次超时后次分钟重试已 `status=200` 投递成功，属良性瞬态告警；
  - `F31`：《2025 账务中台重构 PRD v1.8》已废止，现行 `v2.6` 权威规范明确 `STARTER` 包含配额为 `10,000` 次，严禁误改；
  - `F32`：`INV-202610-0018` 属于已关账 `2026-10`（`CLOSED`）账期，坚决拒绝销售总监私改封账历史库表诉求；
  - `F33`：`ENABLE_V3_BILLING_PIPELINE` 实验管线缺失老租户、合同保底与税擎支持，保持 `False`；
  - `F34`：渠道返佣严格按实付现金核算，运营赠送金视同商业折扣不计提佣金，符合规范；
  - `F35`：新加坡税制 `SG_GST_9_EXCLUSIVE` 境外主体依法不可开具中国增值税专票，保持拦截；
  - `F36`：锦绣集团企业框架协议最低消费保底补齐逻辑符合合同约定，不改；
  - `F37`：遵守最小外科手术原则，不触碰未挂载路由的 `2023/2024` 历史归档死代码目录；
  - `F38`：全额赠送金抵扣账单实付现金为 0 元，依法不予开具增值税发票，保持拦截。

## 2. 核心暗病根因与跨层修复矩阵（`BUG-01`～`BUG-15`）
1. **计量与算价链路（`BUG-01`、`BUG-08`、`BUG-09`、`BUG-10`）**：对齐事件总线 `subscription.plan_changed` 缓存失效、保留双写事件时点套餐并按分段独立核算超额；撤回 `hotfix_20261031` 大额价外税抹零猴子补丁；修复 `runtime_config_loader` 字符串 `'false'` 解析；补齐网关批量接口 UTC 归一化、正整数校验与 `event_id` 幂等。
2. **账本、结算与预览链路（`BUG-02`、`BUG-03`、`BUG-04`、`BUG-11`、`BUG-12`）**：关闭退款洗现模式并同步恢复券批次余额、修复赠送金过期幂等；支付与开票路由开启 `IMMEDIATE` 事务锁与幂等抢占；结算异常回退 `OPEN` 入 `settlement_dlq`，自动结算跳过争议冻结单，`dlq_retry` 仅扣 `total_cents - paid_cents` 未付差额；清除预览 `GET` 锁券副作用并对资费缓存代理做 `deepcopy` 隔离。
3. **财税合规、安全与稳定性链路（`BUG-05`、`BUG-06`、`BUG-07`、`BUG-13`、`BUG-14`、`BUG-15`）**：消除复合条件 IDOR、补齐管理端鉴权与 `realpath` 边界校验、隐藏 500 堆栈并转义前端 XSS；完整保留 `v1` 老租户兼容；拦截 `CLOSED` 账期覆写并修正跨期调账有向符号加法；补齐金税 SDK 游标翻页与含税拆票分位守恒；消除每请求 `event_bus` 订阅泄漏与审计连接句柄泄漏。

## 3. 历史封账红线与 `2026-11` 脏账订正台账
- **封账红线零触碰**：`2026-09`（归档总额 `6402776`）与 `2026-10`（归档总额 `6443588`，含销售施压单 `INV-202610-0018=59900`）原账单分毫无改；`INV-202609-0012` 差额通过 `adj_202609_0012`（`-20000` 分）记入 `2026-11`。
- **开放期 11 处受灾脏账全部修平**：`INV-202611-0019`（`19900`）、`INV-202611-0083`（`34900`）、`INV-202611-0034`（`PAID/59900`）、`INV-202611-0092`（`OPEN/0`）、`t_cust_051`（`cash=10000, promo=10100`）、`t_cust_067`（`promo=0`）、`INV-202611-0978`（`VOID`）、`INV-202611-0118`（`tax=13194, total=233094`）、`INV-202611-0132` & `t_cust_132`（`paid=59900, cash=30100`）、`pg_cust_145`（`ACTIVE/15000`）、`INV-202611-0156`（`4900`）。

## 4. 回归与突变测试验证
新增 `tests/test_regression_fixes.py` 覆盖跨层缓存失效、分段计费、大额价外税、网关跨时区幂等、数电发票全量翻页对账、越权与路径穿越拦截、多线程并发支付及已封账保护，全套单元测试 100% 绿灯通过。
""",
        encoding="utf-8",
    )


if __name__ == "__main__":
    apply_patch(Path(sys.argv[1]).resolve())
