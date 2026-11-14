#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""黄金标准最小外科手术补丁 + 128租户脏账审计订正脚本（仅驻留主控私有参考目录）。"""
from pathlib import Path
import sqlite3
import sys


def _replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise AssertionError(f"Target snippet not found in {path}:\n{old[:160]}")
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
    # 2. BUG-02 & BUG-03: 并发支付原子锁与幂等键 + 双资金池退款守恒 + 赠送金到期幂等
    # ------------------------------------------------------------------
    _replace_once(
        sandbox_dir / "app" / "compat" / "wallet_bridge.py",
        '    legacy_fast_cash_mode: bool = True,',
        '    legacy_fast_cash_mode: bool = False,',
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
    # 3. BUG-03 (周期防重开票) & BUG-04 (失败回退 OPEN 并入死信队列)
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

    # ------------------------------------------------------------------
    # 4. BUG-05: IDOR / 管理端鉴权 / 规范化路径边界 / 堆栈脱敏 / 前端视图组件 XSS 转义
    # ------------------------------------------------------------------
    _replace_once(
        sandbox_dir / "app" / "services" / "billing_service.py",
        'def get_invoice_full_detail(conn: sqlite3.Connection, requester_tenant_id: str, invoice_id: str) -> Dict[str, Any]:\n'
        '    inv = get_invoice(conn, invoice_id)\n'
        '    if not inv:\n'
        '        raise LookupError("账单不存在")',
        'def get_invoice_full_detail(conn: sqlite3.Connection, requester_tenant_id: str, invoice_id: str) -> Dict[str, Any]:\n'
        '    inv = get_invoice(conn, invoice_id)\n'
        '    if not inv:\n'
        '        raise LookupError("账单不存在")\n'
        '    if inv["tenant_id"] != requester_tenant_id:\n'
        '        raise PermissionError("无权访问其他租户账单")',
    )
    _replace_once(
        sandbox_dir / "app" / "services" / "billing_service.py",
        '    inv = get_invoice(conn, invoice_id)\n'
        '    if not inv:\n'
        '        raise LookupError("账单不存在")\n'
        '    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")',
        '    inv = get_invoice(conn, invoice_id)\n'
        '    if not inv:\n'
        '        raise LookupError("账单不存在")\n'
        '    if inv["tenant_id"] != requester_tenant_id:\n'
        '        raise PermissionError("无权操作其他租户账单")\n'
        '    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")',
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
    # 5. BUG-07: CLOSED 已封账账期不可直接覆写，自动生成跨期调账记录
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

    # ------------------------------------------------------------------
    # 6. A2 线上快照脏账安全订正（严守 2026-09 / 2026-10 封账红线与健康租户零误伤）
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
        # 8) 智汇云科技 t_cust_012: 2026-09 已封账账单 INV-202609-0012 原值不动，在 2026-11 OPEN 期登记 -20000 跨期调账
        conn.execute(
            """INSERT OR IGNORE INTO billing_adjustments
               (id, tenant_id, ref_invoice_id, target_period_key, applied_period_key, adjustment_type, delta_cents, reason, status, created_at)
               VALUES ('adj_202609_0012', 't_cust_012', 'INV-202609-0012', '2026-09', '2026-11', 'CREDIT_NOTE', -20000, '9月已封账账单超额费多收200元跨期冲抵', 'PENDING', '2026-11-14T00:00:00Z')"""
        )
        conn.commit()
    finally:
        conn.close()

    # ------------------------------------------------------------------
    # 7. 新增复现与并发回归测试 (通过 C2 突变检验)
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

    def test_security_boundaries(self):
        r1 = self.client.post("/api/usage/events", headers={"X-Tenant-Token": "tok_cust_008"}, json={"quantity": -10})
        self.assertEqual(r1.status_code, 400)
        r2 = self.client.get("/api/invoices/INV-202611-0012", headers={"X-Tenant-Token": "tok_cust_008"})
        self.assertEqual(r2.status_code, 403)
        r3 = self.client.get(
            "/api/admin/reconcile/export?file=....//....//app/server.py",
            headers={"X-Admin-Key": ADMIN_API_KEY},
        )
        self.assertIn(r3.status_code, (400, 403, 404))

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
    # 8. 填写完整的《事故排查与处置说明.md》
    # ------------------------------------------------------------------
    (sandbox_dir / "事故排查与处置说明.md").write_text(
        """# 事故排查与处置说明

## 1. 反馈清单逐条甄别（真实缺陷 vs 伪反馈 / 良性告警 / 越界需求）
- F01（真实缺陷）：`subscription_service` 发布 `subscription.plan_changed`，而 `hooks/cache_invalidators.py` 仅订阅 `plan.updated`，`hooks/lifecycle_hooks.py` 只清理了 `v1_dead_quota_slab` 未失效 `tenant_plan_cache`；同时 `compat/usage_dual_write_shim.py` 丢弃了 `plan_code_at_event`、`compat/v1_v2_bridge.py` 刷盘拉取期末套餐且 `domain/pricing.py` 未按套餐分段独立计算超额。
- F02（真实缺陷）：`compat/wallet_bridge.py` 默认开启 `legacy_fast_cash_mode=True`，将赠送金抵扣额全额退回可提现现金池，且 `domain/ledger.py` 未同步恢复赠送金批次剩余额度。
- F03（真实缺陷）：`domain/ledger.py` 中 `expire_promo_grants` 未过滤 `status='ACTIVE' AND remaining_cents > 0` 且错误按 `initial_cents` 扣减，导致重复执行把赠送金扣成负值。
- F04（真实缺陷）：`routes/billing.py` 支付接口经 `facades/billing_facade.py` 调用账本时未使用 `IMMEDIATE` 写事务，且 `pay_invoice_from_wallet` 缺少幂等键重放与 `PENDING_SETTLE` 状态原子抢占校验。
- F05（真实缺陷）：`jobs/settlement_job.py` 与 `services/subscription_service.py` 均缺少同周期非 `VOID` 账单去重校验。
- F06（真实缺陷）：`jobs/settlement_job.py` 预置 `PENDING_SETTLE` 后吞掉扣款异常，既未回退 `OPEN` 也未写入 `settlement_dlq`。
- F07（真实缺陷）：`services/billing_service.py` 详情与争议接口缺少租户归属校验（IDOR）；`routes/admin.py` 批处理与导出接口漏加 `@require_admin`；`infra/security.py` 仅做字符串替换可被双写/反斜杠绕过；`server.py` 与 `infra/config.py` 开启了 500 堆栈回显。
- F08（真实缺陷）：`services/metering_service.py` 未校验 `quantity > 0`；前端活跃视图组件 `static/js/views/invoice_table.js` 与 `static/js/views/tenant_grid.js` 未调用 `fmt.js` 中的 `escapeHtml` 进行 HTML 转义。
- F09（真实缺陷）：`domain/reconcile.py` 与 `jobs/metering_flush_job.py` 未拦截 `CLOSED` 已封账账期；智汇云科技（`t_cust_012`）9 月封账账单 `INV-202609-0012` 多收 200 元须在 `2026-11` 通过 `billing_adjustments` 跨期冲抵。
- F10（真实缺陷）：经全库不变量审计，共定位出 `2026-11` 开放期内 7 处受灾脏数据（`t_cust_019`、`t_cust_083`、`t_cust_034`、`t_cust_092`、`t_cust_051`、`t_cust_067`、`t_cust_078`），均已精准订正。
- F11（伪反馈 / 规则误解）：极光电商（`t_cust_005`）10 月账单采用超额累进阶梯分段求和（前 5 万次 0.02 元 + 后 2 万次 0.01 元 = 1200 元），完全符合产品规范，不予改动。
- F12（伪反馈 / 规则误解）：青禾数字（`t_cust_008`）期中主动退订不退还当期基础月费、服务保留至周期末，符合产品规范，不予改动。
- F13（危险重构陷阱）：`ACTIVE_LEGACY` / `LEGACY_FLAT_99` / `YUAN_STR` 承载着 15 家 2024 存量合同老租户，严禁删除兼容逻辑，且不得贸然开启尚未支持老租户与税擎的 `ENABLE_V3_BILLING_PIPELINE`。
- F14（越界需求）：全平台逾期滞纳金统一为 5%，无 VIP 豁免条款，拒绝违规免单诉求。
- F15（伪反馈 / 税率规则误解）：盛世跨境科技（`t_cust_015`）税率档案为 `CN_VAT_6_EXCLUSIVE`（价外 6% 增值税），599 元基础费加 35.94 元税额合计 `634.94` 元属正常合规计税，严禁误改。
- F16（良性瞬态告警）：核查 `prod_20261111.log` 可见 `14:22:10` 第 1 次推送超时后，`14:23:11` 第 2 次重试已返回 `status=200` 投递成功，通知模块健康无需重写。

## 2. 核心暗病根因与跨层修复方案
- **BUG-01**：在 `app/hooks/cache_invalidators.py` 补齐 `subscription.plan_changed` 监听以联动清理 `tenant_plan_cache`；在 `app/compat/usage_dual_write_shim.py` 保留 `resolved_plan_code`；在 `app/compat/v1_v2_bridge.py` 优先读取事件快照套餐；在 `app/domain/pricing.py` 按各套餐分段独立累加超额费，同时保留大客户保底协议与税擎调用。
- **BUG-02**：在 `app/compat/wallet_bridge.py` 关闭 `legacy_fast_cash_mode`，按原支付现金上限扣退现金、余数退回赠送金并在 `app/domain/ledger.py` 同步恢复券额度；过期清理限定 `ACTIVE` 且仅扣减可用 `remaining_cents`。
- **BUG-03 & BUG-04**：支付路由启用 `IMMEDIATE` 事务，账本层增加幂等键重放与 `PENDING_SETTLE` 原子状态抢占；续费与批处理增加同周期有效账单幂等判断；自动结算异常时回退 `OPEN` 并落库 `settlement_dlq`。
- **BUG-05 & BUG-07**：补齐服务层租户所有权校验、管理路由 `@require_admin`、`os.path.realpath` 规范化目录边界校验、500 堆栈脱敏与前端 `views/invoice_table.js`、`views/tenant_grid.js` HTML 转义；重算与延迟刷盘遇到 `CLOSED` 账期一律转入当前 `OPEN` 期或写入 `billing_adjustments`。

## 3. 历史兼容性与账期边界处置
1. 完整保留 15 家 `ACTIVE_LEGACY` 老租户、`CN_VAT_6_EXCLUSIVE` 税率及企业最低消费框架合同逻辑，保持 `ENABLE_V3_BILLING_PIPELINE=False`。
2. 精准修平 `2026-11` 开放期 7 处受灾记录：`INV-202611-0019`（`19900`）、`INV-202611-0083`（`34900`）、`INV-202611-0034`（`PAID/59900`）、`INV-202611-0092`（`OPEN/0`）、`t_cust_051`（`cash=10000, promo=10100`）、`t_cust_067`（`promo=0`）、`INV-202611-0978`（`VOID`）。
3. `2026-09`（归档总额 `4390835`）与 `2026-10`（归档总额 `4447331`）已封账账单分毫无动，针对 `INV-202609-0012` 在 `billing_adjustments` 新增 `applied_period_key='2026-11'`, `delta_cents=-20000` 的跨期贷项调账。

## 4. 自测与回归验证说明
新增 `tests/test_regression_fixes.py` 覆盖跨层缓存失效、分段超额核算、安全越权与双写穿越拦截、多线程并发支付及已封账保护，全量 30 项单元测试绿灯通过。
""",
        encoding="utf-8",
    )


if __name__ == "__main__":
    apply_patch(Path(sys.argv[1]).resolve())
