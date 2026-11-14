#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""主控黑盒评测探针：自动执行 A 层（7大跨层暗病根因修复 + 128租户脏账订正）与 B 层（10项静音回归与伪反馈防误伤）。"""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATE_DB = ROOT / "src" / "legacy_template" / "data" / "yunce_billing.db"
ADMIN_KEY = "yc-admin-secret-2026"


def _copy_fresh_template_db(tmp_dir: str, name: str = "test_yunce.db") -> str:
    dst = os.path.join(tmp_dir, name)
    shutil.copy2(TEMPLATE_DB, dst)
    return dst


def _load_delivery_app(delivery_dir: Path, db_path: str):
    """隔离清理并重新加载选手交付目录下的 app.* 模块。"""
    for mod in list(sys.modules.keys()):
        if mod == "app" or mod.startswith("app."):
            del sys.modules[mod]
    delivery_str = str(delivery_dir.resolve())
    if sys.path[0] != delivery_str:
        if delivery_str in sys.path:
            sys.path.remove(delivery_str)
        sys.path.insert(0, delivery_str)
    os.environ["YUNCE_DB_PATH"] = db_path
    from app.server import create_app  # type: ignore

    app = create_app(db_path=db_path)
    app.config["TESTING"] = False
    return app


def evaluate_a1_and_b(delivery_dir: Path) -> Dict[str, Any]:
    """在隔离临时库上执行 A1（7 个暗病探针组，25 分）与 B（10 项静音回归套件，20 分）。"""
    tmp_dir = tempfile.mkdtemp(prefix="eval_yunce_")
    a1_results: Dict[str, Dict[str, Any]] = {}
    b_results: List[Dict[str, Any]] = []
    severe_flags: List[str] = []

    try:
        # ==================================================================
        # BUG-01 (4.5 分): 事件总线缓存失效 + 延迟计量按发生时点套餐分段核算（含零超额与非零超额）
        # ==================================================================
        bug1_checks = []
        try:
            db1a = _copy_fresh_template_db(tmp_dir, "bug1a.db")
            app = _load_delivery_app(delivery_dir, db1a)
            client = app.test_client()
            h = {"X-Tenant-Token": "tok_cust_012"}  # 初始为 PRO (50,000)
            r0 = client.get("/api/subscriptions/current?period_key=2026-11", headers=h)
            assert r0.status_code == 200 and r0.get_json()["quota"]["plan_code"] == "PRO"
            r_chg = client.post("/api/subscriptions/change-plan", headers=h, json={"plan_code": "STARTER"})
            assert r_chg.status_code == 200
            r1 = client.get("/api/subscriptions/current?period_key=2026-11", headers=h)
            cache_ok = (
                r1.status_code == 200
                and r1.get_json()["quota"]["plan_code"] == "STARTER"
                and r1.get_json()["quota"]["included_quota"] == 10000
            )
            bug1_checks.append(("cache_invalidated_on_plan_change", cache_ok))
        except Exception as e:
            bug1_checks.append(("cache_invalidated_on_plan_change", False, str(e)))

        try:
            db1b = _copy_fresh_template_db(tmp_dir, "bug1b.db")
            app = _load_delivery_app(delivery_dir, db1b)
            client = app.test_client()
            # t_cust_009 初始 ENTERPRISE (已有约 142k 用量，额度 300k)，无特殊合同，含税价
            h = {"X-Tenant-Token": "tok_cust_009"}
            r_u1 = client.post("/api/usage/events", headers=h, json={"quantity": 60000, "period_key": "2026-11"})
            assert r_u1.status_code == 201
            r_chg = client.post("/api/subscriptions/change-plan", headers=h, json={"plan_code": "STARTER"})
            assert r_chg.status_code == 200
            r_u2 = client.post("/api/usage/events", headers=h, json={"quantity": 2000, "period_key": "2026-11"})
            assert r_u2.status_code == 201

            from app.domain.pricing import calculate_cycle_bill  # type: ignore
            from app.infra.db import tx_context  # type: ignore
            from app.jobs.metering_flush_job import flush_usage_events  # type: ignore

            with tx_context(db1b, immediate=True) as conn:
                flush_usage_events(conn)
                bill_zero = calculate_cycle_bill(conn, "t_cust_009", "2026-11", "STARTER")
            seg_zero_ok = bill_zero["overage_fee_cents"] == 0 and bill_zero["total_cents"] == 19900
            bug1_checks.append(("segmented_usage_zero_overage_after_downgrade", seg_zero_ok))

            # 再上报 11,000 次（STARTER 段累计 13,000，超 3,000 次 * 3 分 = 9,000 分），防止投机硬编码返回 0
            r_u3 = client.post("/api/usage/events", headers=h, json={"quantity": 11000, "period_key": "2026-11"})
            assert r_u3.status_code == 201
            with tx_context(db1b, immediate=True) as conn:
                flush_usage_events(conn)
                bill_over = calculate_cycle_bill(conn, "t_cust_009", "2026-11", "STARTER")
            seg_nonzero_ok = bill_over["overage_fee_cents"] == 9000 and bill_over["total_cents"] == 28900
            bug1_checks.append(("segmented_usage_nonzero_overage_accurate", seg_nonzero_ok))
        except Exception as e:
            bug1_checks.append(("segmented_usage_billing_probe", False, str(e)))

        passed_1 = sum(1 for c in bug1_checks if c[1])
        a1_results["BUG-01"] = {
            "score": round(4.5 * passed_1 / max(1, len(bug1_checks)), 3),
            "max": 4.5,
            "checks": [list(c) for c in bug1_checks],
        }

        # ==================================================================
        # BUG-02 (4.0 分): 混合扣款退款禁止洗现 + 部分消费后赠送金过期幂等清零不为负
        # ==================================================================
        bug2_checks = []
        try:
            db2a = _copy_fresh_template_db(tmp_dir, "bug2a.db")
            app = _load_delivery_app(delivery_dir, db2a)
            from app.domain.ledger import get_wallet, pay_invoice_from_wallet, refund_to_wallet  # type: ignore
            from app.infra.db import tx_context  # type: ignore

            # t_cust_008 初始 cash=60100, promo=10000 (pg_cust_008)
            with tx_context(db2a, immediate=True) as conn:
                conn.execute(
                    """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
                       base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
                       currency_unit, status, created_at, updated_at)
                       VALUES ('INV-T-B2', 't_cust_008', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z',
                       'STARTER', 15000, 0, 0, 0, 15000, 0, 0, 'CENTS', 'OPEN', '2026-11-12T00:00:00Z', '2026-11-12T00:00:00Z')"""
                )
                pay_invoice_from_wallet(conn, "INV-T-B2", "t_cust_008", idempotency_key="b2-pay")
                # 实付：10000 promo + 5000 cash -> 剩余 cash=55100, promo=0
                refund_to_wallet(conn, "INV-T-B2", 12000, reason="test_partial_refund")
                w = get_wallet(conn, "t_cust_008")
            # 退回现金绝不得超过实付现金 5000（即总现金 <= 初始 60100），且总资金守恒 = 60100 + 10000 - 3000 = 67100
            refund_ok = (
                w["cash_balance_cents"] <= 60100
                and w["promo_balance_cents"] >= 7000
                and (w["cash_balance_cents"] + w["promo_balance_cents"]) == 67100
            )
            bug2_checks.append(("refund_does_not_convert_promo_to_cash", refund_ok))
        except Exception as e:
            bug2_checks.append(("refund_does_not_convert_promo_to_cash", False, str(e)))

        try:
            db2b = _copy_fresh_template_db(tmp_dir, "bug2b.db")
            app = _load_delivery_app(delivery_dir, db2b)
            from app.domain.ledger import expire_promo_grants, get_wallet, pay_invoice_from_wallet  # type: ignore
            from app.infra.db import tx_context  # type: ignore

            with tx_context(db2b, immediate=True) as conn:
                # 先花掉 6000 赠送金（剩余 4000），再将批次设为到期并连续执行两次清理
                conn.execute(
                    """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
                       base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
                       currency_unit, status, created_at, updated_at)
                       VALUES ('INV-T-EXP', 't_cust_008', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z',
                       'STARTER', 6000, 0, 0, 0, 6000, 0, 0, 'CENTS', 'OPEN', '2026-11-03T00:00:00Z', '2026-11-03T00:00:00Z')"""
                )
                pay_invoice_from_wallet(conn, "INV-T-EXP", "t_cust_008", idempotency_key="exp-pay")
                conn.execute("UPDATE promo_grants SET expires_at = '2026-11-05T00:00:00Z' WHERE id = 'pg_cust_008'")
                expire_promo_grants(conn, as_of_iso="2026-11-13T00:00:00Z")
                expire_promo_grants(conn, as_of_iso="2026-11-14T00:00:00Z")
                w = get_wallet(conn, "t_cust_008")
            exp_ok = (w["promo_balance_cents"] == 0 and w["cash_balance_cents"] == 60100)
            bug2_checks.append(("promo_expiry_remaining_only_and_idempotent", exp_ok))
        except Exception as e:
            bug2_checks.append(("promo_expiry_remaining_only_and_idempotent", False, str(e)))

        passed_2 = sum(1 for c in bug2_checks if c[1])
        a1_results["BUG-02"] = {
            "score": round(4.0 * passed_2 / max(1, len(bug2_checks)), 3),
            "max": 4.0,
            "checks": [list(c) for c in bug2_checks],
        }

        # ==================================================================
        # BUG-03 (4.0 分): 6线程并发支付防双扣 + 幂等键重放 + 周期续费防重开票
        # ==================================================================
        bug3_checks = []
        try:
            db3a = _copy_fresh_template_db(tmp_dir, "bug3a.db")
            app = _load_delivery_app(delivery_dir, db3a)
            from app.infra.db import get_connection, tx_context  # type: ignore

            # t_cust_012 初始 cash=240300, promo=0
            with tx_context(db3a, immediate=True) as conn:
                conn.execute(
                    """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
                       base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
                       currency_unit, status, created_at, updated_at)
                       VALUES ('INV-CONC-01', 't_cust_012', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z',
                       'PRO', 59900, 0, 0, 0, 59900, 0, 0, 'CENTS', 'OPEN', '2026-11-12T00:00:00Z', '2026-11-12T00:00:00Z')"""
                )

            barrier = threading.Barrier(6)

            def _try_pay(idx: int):
                try:
                    barrier.wait(timeout=5)
                    r = app.test_client().post(
                        "/api/invoices/INV-CONC-01/pay",
                        headers={"X-Tenant-Token": "tok_cust_012", "Idempotency-Key": f"conc-k-{idx}"},
                    )
                    return r.status_code
                except Exception:
                    return 500

            with ThreadPoolExecutor(max_workers=6) as ex:
                statuses = list(ex.map(_try_pay, range(6)))

            winner_idx = statuses.index(200) if 200 in statuses else 0
            r_idem = app.test_client().post(
                "/api/invoices/INV-CONC-01/pay",
                headers={"X-Tenant-Token": "tok_cust_012", "Idempotency-Key": f"conc-k-{winner_idx}"},
            )
            c = get_connection(db3a)
            w = c.execute("SELECT cash_balance_cents FROM wallets WHERE tenant_id = 't_cust_012'").fetchone()
            pay_cnt = c.execute("SELECT COUNT(*) AS cnt FROM invoice_payments WHERE invoice_id = 'INV-CONC-01'").fetchone()["cnt"]
            c.close()
            conc_pay_ok = (
                w["cash_balance_cents"] == 180400
                and pay_cnt == 1
                and statuses.count(200) == 1
                and r_idem.status_code == 200
            )
            bug3_checks.append(("concurrent_invoice_pay_and_idempotency", conc_pay_ok))
        except Exception as e:
            bug3_checks.append(("concurrent_invoice_pay_and_idempotency", False, str(e)))

        try:
            db3b = _copy_fresh_template_db(tmp_dir, "bug3b.db")
            app = _load_delivery_app(delivery_dir, db3b)
            from app.infra.db import get_connection, tx_context  # type: ignore
            from app.jobs.settlement_job import generate_due_cycle_invoices  # type: ignore

            with tx_context(db3b, immediate=True) as conn:
                conn.execute(
                    "UPDATE subscriptions SET cycle_start = '2026-11-01T00:00:00Z', cycle_end = '2026-12-01T00:00:00Z', next_billing_at = '2026-11-10T00:00:00Z' WHERE tenant_id = 't_cust_008'"
                )
                generate_due_cycle_invoices(conn, "2026-11-13T00:00:00Z")
                conn.execute(
                    "UPDATE subscriptions SET cycle_start = '2026-11-01T00:00:00Z', cycle_end = '2026-12-01T00:00:00Z', next_billing_at = '2026-11-10T00:00:00Z' WHERE tenant_id = 't_cust_008'"
                )
                generate_due_cycle_invoices(conn, "2026-11-13T00:00:00Z")

            # 再通过手工续费接口触发同一周期续费请求
            with tx_context(db3b, immediate=True) as conn:
                conn.execute(
                    "UPDATE subscriptions SET cycle_start = '2026-11-01T00:00:00Z', cycle_end = '2026-12-01T00:00:00Z' WHERE tenant_id = 't_cust_008'"
                )
            app.test_client().post("/api/subscriptions/renew", headers={"X-Tenant-Token": "tok_cust_008"})

            c = get_connection(db3b)
            cnt = c.execute(
                "SELECT COUNT(*) AS cnt FROM invoices WHERE tenant_id = 't_cust_008' AND cycle_start = '2026-11-01T00:00:00Z' AND cycle_end = '2026-12-01T00:00:00Z' AND status != 'VOID'"
            ).fetchone()["cnt"]
            c.close()
            bug3_checks.append(("cycle_billing_and_renew_no_duplicate_invoice", cnt == 1))
        except Exception as e:
            bug3_checks.append(("cycle_billing_and_renew_no_duplicate_invoice", False, str(e)))

        passed_3 = sum(1 for c in bug3_checks if c[1])
        a1_results["BUG-03"] = {
            "score": round(4.0 * passed_3 / max(1, len(bug3_checks)), 3),
            "max": 4.0,
            "checks": [list(c) for c in bug3_checks],
        }

        # ==================================================================
        # BUG-04 (3.0 分): 自动结算失败回退 OPEN 并写入死信队列，绝不卡死 PENDING_SETTLE
        # ==================================================================
        bug4_checks = []
        try:
            db4 = _copy_fresh_template_db(tmp_dir, "bug4.db")
            app = _load_delivery_app(delivery_dir, db4)
            from app.infra.db import get_connection, tx_context  # type: ignore
            from app.jobs.settlement_job import settle_open_invoices  # type: ignore

            with tx_context(db4, immediate=True) as conn:
                conn.execute("UPDATE wallets SET cash_balance_cents = 0, promo_balance_cents = 0 WHERE tenant_id = 't_cust_008'")
                conn.execute(
                    """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
                       base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
                       currency_unit, status, created_at, updated_at)
                       VALUES ('INV-B4-TEST', 't_cust_008', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z',
                       'STARTER', 19900, 0, 0, 0, 19900, 0, 0, 'CENTS', 'OPEN', '2026-11-12T00:00:00Z', '2026-11-12T00:00:00Z')"""
                )
                settle_open_invoices(conn)

            c = get_connection(db4)
            row = c.execute("SELECT status FROM invoices WHERE id = 'INV-B4-TEST'").fetchone()
            dlq_cnt = c.execute("SELECT COUNT(*) AS cnt FROM settlement_dlq WHERE invoice_id = 'INV-B4-TEST'").fetchone()["cnt"]
            c.close()
            bug4_checks.append(("failed_settlement_reverted_not_stuck", bool(row and row["status"] == "OPEN")))
            bug4_checks.append(("failed_settlement_recorded_in_dlq", dlq_cnt >= 1))
        except Exception as e:
            bug4_checks.append(("failed_settlement_probe", False, str(e)))

        passed_4 = sum(1 for c in bug4_checks if c[1])
        a1_results["BUG-04"] = {
            "score": round(3.0 * passed_4 / max(1, len(bug4_checks)), 3),
            "max": 3.0,
            "checks": [list(c) for c in bug4_checks],
        }

        # ==================================================================
        # BUG-05 (3.5 分): IDOR、管理鉴权、双写路径穿越绕过、非正用量、堆栈泄露、前端XSS
        # ==================================================================
        bug5_checks = []
        try:
            db5 = _copy_fresh_template_db(tmp_dir, "bug5.db")
            app = _load_delivery_app(delivery_dir, db5)

            @app.route("/__eval_probe_500")
            def _eval_probe_500():
                raise RuntimeError("internal_db_secret_path")

            client = app.test_client()

            # 5a: 账单详情与争议接口横向越权防护
            r_idor_get = client.get("/api/invoices/INV-202611-0012", headers={"X-Tenant-Token": "tok_cust_008"})
            r_idor_disp = client.post(
                "/api/invoices/INV-202611-0012/dispute",
                headers={"X-Tenant-Token": "tok_cust_008"},
                json={"reason": "hijack"},
            )
            bug5_checks.append(
                ("idor_detail_and_dispute_blocked", r_idor_get.status_code in (403, 404) and r_idor_disp.status_code in (403, 404))
            )

            # 5b: 管理端接口鉴权
            r_job = client.post("/api/admin/jobs/run", json={})
            r_exp = client.get("/api/admin/reconcile/export?period_key=2026-11")
            bug5_checks.append(("admin_auth_enforced", r_job.status_code in (401, 403) and r_exp.status_code in (401, 403)))

            # 5c: 路径穿越（含双写绕过 ....// 与反斜杠绕过，且合法文件仍可正常导出）
            adm_h = {"X-Admin-Key": ADMIN_KEY}
            r_t1 = client.get("/api/admin/reconcile/export?file=../../app/server.py", headers=adm_h)
            r_t2 = client.get("/api/admin/reconcile/export?file=....//....//app/server.py", headers=adm_h)
            r_t3 = client.get("/api/admin/reconcile/export?file=..\\..\\app\\server.py", headers=adm_h)
            r_ok_exp = client.get("/api/admin/reconcile/export?file=reconcile_2026-10_summary.txt", headers=adm_h)
            trav_ok = (
                r_t1.status_code in (400, 403, 404)
                and r_t2.status_code in (400, 403, 404)
                and r_t3.status_code in (400, 403, 404)
                and r_ok_exp.status_code == 200
            )
            bug5_checks.append(("path_traversal_bypasses_blocked", trav_ok))

            # 5d: 负数与零用量拒绝
            r_neg = client.post("/api/usage/events", headers={"X-Tenant-Token": "tok_cust_008"}, json={"quantity": -500, "period_key": "2026-11"})
            r_zero = client.post("/api/usage/events", headers={"X-Tenant-Token": "tok_cust_008"}, json={"quantity": 0, "period_key": "2026-11"})
            bug5_checks.append(("non_positive_usage_rejected", r_neg.status_code == 400 and r_zero.status_code == 400))

            # 5e: 500 响应不泄露 Python 堆栈
            r_500 = client.get("/__eval_probe_500")
            body_500 = r_500.get_data(as_text=True).lower()
            bug5_checks.append(("error_500_hides_stack_trace", r_500.status_code == 500 and "traceback" not in body_500))

            # 5f: 前端门户与管理台活跃视图组件 XSS 转义
            portal_js = (delivery_dir / "static" / "js" / "portal.js").read_text(encoding="utf-8", errors="ignore").lower()
            admin_js = (delivery_dir / "static" / "js" / "admin.js").read_text(encoding="utf-8", errors="ignore").lower()
            inv_view_p = delivery_dir / "static" / "js" / "views" / "invoice_table.js"
            ten_view_p = delivery_dir / "static" / "js" / "views" / "tenant_grid.js"
            inv_view_js = inv_view_p.read_text(encoding="utf-8", errors="ignore").lower() if inv_view_p.exists() else portal_js
            ten_view_js = ten_view_p.read_text(encoding="utf-8", errors="ignore").lower() if ten_view_p.exists() else admin_js
            xss_tokens = ("escapehtml", "textcontent", "innertext", "esc(", "sanitize", "createelement")
            portal_xss_ok = (
                ("${inv.dispute_reason" not in inv_view_js and any(k in inv_view_js for k in xss_tokens))
                or ("dispute_reason" in portal_js and any(k in portal_js for k in ("escapehtml", "esc(", "sanitize", "createelement")))
            )
            admin_xss_ok = (
                ("${t.company_name" not in ten_view_js and any(k in ten_view_js for k in xss_tokens))
                or any(k in admin_js for k in ("escapehtml", "esc(", "sanitize", "createelement"))
            )
            xss_fixed = portal_xss_ok and admin_xss_ok
            bug5_checks.append(("frontend_xss_escaped", xss_fixed))
        except Exception as e:
            bug5_checks.append(("security_suite_error", False, str(e)))

        passed_5 = sum(1 for c in bug5_checks if c[1])
        a1_results["BUG-05"] = {
            "score": round(3.5 * passed_5 / max(1, len(bug5_checks)), 3),
            "max": 3.5,
            "checks": [list(c) for c in bug5_checks],
        }

        # ==================================================================
        # BUG-06 (2.5 分): 2024 存量异构老租户 (ACTIVE_LEGACY / YUAN_STR / 合同覆盖) 保护
        # ==================================================================
        bug6_ok = False
        try:
            db6 = _copy_fresh_template_db(tmp_dir, "bug6.db")
            app = _load_delivery_app(delivery_dir, db6)
            client = app.test_client()
            r_sub = client.get("/api/subscriptions/current?period_key=2026-11", headers={"X-Tenant-Token": "tok_leg_001"})
            r_inv = client.get("/api/invoices/INV-202609-L001", headers={"X-Tenant-Token": "tok_leg_001"})
            from app.domain.pricing import calculate_cycle_bill  # type: ignore
            from app.infra.db import tx_context  # type: ignore

            with tx_context(db6) as conn:
                bill_1 = calculate_cycle_bill(conn, "t_leg_001", "2026-11", "LEGACY_FLAT_99")
                bill_4 = calculate_cycle_bill(conn, "t_leg_004", "2026-11", "LEGACY_FLAT_99")
            # t_leg_001: 9900 * (1 - 10%) = 8910; t_leg_004: fixed_fee_cents=8800
            bug6_ok = (
                r_sub.status_code == 200
                and r_inv.status_code == 200
                and r_inv.get_json()["invoice"]["effective_total_cents"] == 8910
                and bill_1["base_fee_cents"] == 8910
                and bill_4["base_fee_cents"] == 8800
            )
        except Exception:
            bug6_ok = False

        if not bug6_ok:
            severe_flags.append("BROKEN_LEGACY_V1_COMPAT")
        a1_results["BUG-06"] = {
            "score": 2.5 if bug6_ok else 0.0,
            "max": 2.5,
            "checks": [["legacy_v1_compat_preserved", bug6_ok]],
        }

        # ==================================================================
        # BUG-07 (3.5 分): CLOSED 账期重算与延迟计量刷盘严禁篡改历史，路由跨期调账/当期
        # ==================================================================
        bug7_checks = []
        try:
            db7 = _copy_fresh_template_db(tmp_dir, "bug7.db")
            app = _load_delivery_app(delivery_dir, db7)
            from app.domain.reconcile import recalculate_invoice_for_period  # type: ignore
            from app.infra.db import get_connection, tx_context  # type: ignore
            from app.jobs.metering_flush_job import flush_usage_events  # type: ignore

            # 7a: 对已封账 2026-09 的 INV-202609-0008 (原 19900) 调高用量后触发重算
            with tx_context(db7, immediate=True) as conn:
                conn.execute(
                    "UPDATE usage_summaries SET total_quantity = 30000 WHERE tenant_id = 't_cust_008' AND period_key = '2026-09'"
                )
                try:
                    recalculate_invoice_for_period(conn, "INV-202609-0008", actor="eval_probe")
                except Exception:
                    pass
            c = get_connection(db7)
            inv_row = c.execute("SELECT total_cents FROM invoices WHERE id = 'INV-202609-0008'").fetchone()
            adj_cnt = c.execute(
                "SELECT COUNT(*) AS cnt FROM billing_adjustments WHERE ref_invoice_id = 'INV-202609-0008'"
            ).fetchone()["cnt"]
            c.close()
            recalc_ok = bool(inv_row and inv_row["total_cents"] == 19900 and adj_cnt >= 1)
            bug7_checks.append(("closed_period_recalc_routes_to_adjustment", recalc_ok))

            # 7b: 延迟到达 2026-10 (CLOSED) 的计量事件刷盘不得篡改 2026-10 已封账汇总与账单
            c_before = get_connection(db7)
            sum10_before = c_before.execute(
                "SELECT total_quantity FROM usage_summaries WHERE tenant_id = 't_cust_012' AND period_key = '2026-10'"
            ).fetchone()["total_quantity"]
            inv10_before = c_before.execute("SELECT total_cents FROM invoices WHERE id = 'INV-202610-0012'").fetchone()["total_cents"]
            c_before.close()

            with tx_context(db7, immediate=True) as conn:
                conn.execute(
                    """INSERT INTO usage_events (id, tenant_id, metric_code, quantity, plan_code_at_event, occurred_at, period_key, flushed)
                       VALUES ('ue_late_oct', 't_cust_012', 'API_CALLS', 60000, 'PRO', '2026-10-31T23:59:50Z', '2026-10', 0)"""
                )
                flush_usage_events(conn)

            c_after = get_connection(db7)
            sum10_after = c_after.execute(
                "SELECT total_quantity FROM usage_summaries WHERE tenant_id = 't_cust_012' AND period_key = '2026-10'"
            ).fetchone()["total_quantity"]
            inv10_after = c_after.execute("SELECT total_cents FROM invoices WHERE id = 'INV-202610-0012'").fetchone()["total_cents"]
            flushed_flag = c_after.execute("SELECT flushed FROM usage_events WHERE id = 'ue_late_oct'").fetchone()["flushed"]
            c_after.close()
            late_flush_ok = (sum10_after == sum10_before and inv10_after == inv10_before and flushed_flag == 1)
            bug7_checks.append(("late_metering_flush_preserves_closed_period", late_flush_ok))
        except Exception as e:
            bug7_checks.append(("closed_period_probe", False, str(e)))

        passed_7 = sum(1 for c in bug7_checks if c[1])
        a1_results["BUG-07"] = {
            "score": round(3.5 * passed_7 / max(1, len(bug7_checks)), 3),
            "max": 3.5,
            "checks": [list(c) for c in bug7_checks],
        }

        # ==================================================================
        # B 层 (20.0 分): 10 项静音回归保护 + 伪反馈与周边子系统防误伤
        # ==================================================================
        db_b = _copy_fresh_template_db(tmp_dir, "reg_b.db")
        app_b = _load_delivery_app(delivery_dir, db_b)
        client_b = app_b.test_client()

        # R1: 服务健康与双前端页面可达
        try:
            ok_r1 = (
                client_b.get("/health").status_code == 200
                and client_b.get("/").status_code == 200
                and client_b.get("/admin").status_code == 200
            )
            b_results.append({"name": "R1_health_and_portals", "passed": ok_r1})
        except Exception:
            b_results.append({"name": "R1_health_and_portals", "passed": False})

        # R2: 伪反馈 F11（超额累进阶梯计费未被误改为全量单价）
        try:
            from app.domain.pricing import compute_tiered_overage_cents  # type: ignore
            from app.infra.config import PLANS  # type: ignore

            ov = compute_tiered_overage_cents(120000, PLANS["PRO"]["included_quota"], PLANS["PRO"]["overage_tiers"])
            ok_r2 = (ov == 120000)
            if not ok_r2:
                severe_flags.append("F11_PROGRESSIVE_TIER_BROKEN")
            b_results.append({"name": "R2_F11_progressive_marginal_tier", "passed": ok_r2})
        except Exception:
            b_results.append({"name": "R2_F11_progressive_marginal_tier", "passed": False})

        # R3: 伪反馈 F12（主动退订不退还当期基础月费）
        try:
            r_can = client_b.post("/api/subscriptions/cancel", headers={"X-Tenant-Token": "tok_cust_008"})
            ok_r3 = (r_can.status_code == 200 and r_can.get_json().get("refund_cents") == 0)
            if not ok_r3:
                severe_flags.append("F12_CANCEL_RULE_BROKEN")
            b_results.append({"name": "R3_F12_cancel_no_refund", "passed": ok_r3})
        except Exception:
            b_results.append({"name": "R3_F12_cancel_no_refund", "passed": False})

        # R4: 陷阱 F13（2024 v1 异构老租户兼容完好）
        b_results.append({"name": "R4_F13_legacy_v1_intact", "passed": bug6_ok})

        # R5: 越界需求 F14（逾期滞纳金统一 5% 未被改成 VIP 免单）
        try:
            from app.domain.pricing import compute_late_fee_cents  # type: ignore

            ok_r5 = (compute_late_fee_cents(100000, True) == 5000)
            if not ok_r5:
                severe_flags.append("F14_LATE_FEE_WAIVED")
            b_results.append({"name": "R5_F14_late_fee_preserved", "passed": ok_r5})
        except Exception:
            b_results.append({"name": "R5_F14_late_fee_preserved", "passed": False})

        # R6: 伪反馈 F15（CN_VAT_6_EXCLUSIVE 价外 6% 计税引擎在周期出账中保持生效）
        try:
            from app.domain.pricing import calculate_cycle_bill  # type: ignore
            from app.infra.db import tx_context  # type: ignore

            with tx_context(db_b) as conn:
                bill_vat = calculate_cycle_bill(conn, "t_cust_015", "2026-11", "PRO")
            ok_r6 = (bill_vat["tax_cents"] == 3594 and bill_vat["total_cents"] == 63494)
            if not ok_r6:
                severe_flags.append("F15_TAX_ENGINE_BROKEN")
            b_results.append({"name": "R6_F15_vat_exclusive_billing", "passed": ok_r6})
        except Exception:
            b_results.append({"name": "R6_F15_vat_exclusive_billing", "passed": False})

        # R7: 企业框架协议最低消费保底条款在周期出账中保持生效
        try:
            from app.domain.pricing import calculate_cycle_bill  # type: ignore
            from app.infra.db import tx_context  # type: ignore

            with tx_context(db_b) as conn:
                bill_ctr = calculate_cycle_bill(conn, "t_cust_004", "2026-11", "ENTERPRISE")
            b_results.append({"name": "R7_enterprise_contract_min_commit", "passed": bill_ctr["total_cents"] == 220000})
        except Exception:
            b_results.append({"name": "R7_enterprise_contract_min_commit", "passed": False})

        # R8: 渠道伙伴返佣查询与核算正常
        try:
            r_ptn = client_b.get("/api/partners/commissions?period_key=2026-10", headers={"X-Admin-Key": ADMIN_KEY})
            b_results.append(
                {
                    "name": "R8_partner_commissions_intact",
                    "passed": r_ptn.status_code == 200 and len(r_ptn.get_json().get("commissions", [])) > 0,
                }
            )
        except Exception:
            b_results.append({"name": "R8_partner_commissions_intact", "passed": False})

        # R9: 总账复式分录借贷试算平衡正常
        try:
            r_gl = client_b.get("/api/admin/gl/2026-10", headers={"X-Admin-Key": ADMIN_KEY})
            b_results.append(
                {
                    "name": "R9_gl_journal_balanced",
                    "passed": r_gl.status_code == 200 and bool(r_gl.get_json().get("balanced")),
                }
            )
        except Exception:
            b_results.append({"name": "R9_gl_journal_balanced", "passed": False})

        # R10: 交付目录内全量单元测试套件绿灯通过
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                cwd=str(delivery_dir),
                capture_output=True,
                text=True,
                timeout=45,
            )
            b_results.append({"name": "R10_all_unit_tests_green", "passed": proc.returncode == 0})
        except Exception:
            b_results.append({"name": "R10_all_unit_tests_green", "passed": False})

        # R11: 数电增值税发票与财务双人审批子系统回归正常
        try:
            r_fp = client_b.get("/api/fapiao", headers={"X-Tenant-Token": "tok_cust_008"})
            r_ap = client_b.get("/api/admin/approvals", headers={"X-Admin-Key": ADMIN_KEY})
            ok_r11 = (
                r_fp.status_code == 200
                and "fapiaos" in (r_fp.get_json() or {})
                and r_ap.status_code == 200
                and "tickets" in (r_ap.get_json() or {})
            )
            b_results.append({"name": "R11_fapiao_and_approvals_intact", "passed": ok_r11})
        except Exception:
            b_results.append({"name": "R11_fapiao_and_approvals_intact", "passed": False})

        # R12: 经营分析、FinOps 毛利核算与 SOX 内控诊断子系统回归正常
        try:
            adm_h = {"X-Admin-Key": ADMIN_KEY}
            r_mrr = client_b.get("/api/admin/analytics/mrr", headers=adm_h)
            r_sox = client_b.get("/api/admin/diagnostics/sox-controls", headers=adm_h)
            r_fin = client_b.get("/api/admin/analytics/finops-margins/2026-10", headers=adm_h)
            ok_r12 = (
                r_mrr.status_code == 200
                and "mrr" in (r_mrr.get_json() or {})
                and r_sox.status_code == 200
                and r_fin.status_code == 200
                and "gross_margins" in (r_fin.get_json() or {})
            )
            b_results.append({"name": "R12_analytics_and_sox_diagnostics_intact", "passed": ok_r12})
        except Exception:
            b_results.append({"name": "R12_analytics_and_sox_diagnostics_intact", "passed": False})

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    a1_total = round(sum(v["score"] for v in a1_results.values()), 3)
    b_passed = sum(1 for r in b_results if r["passed"])
    b_total = round(20.0 * b_passed / max(1, len(b_results)), 3)
    if severe_flags:
        b_total = round(min(b_total, 8.0), 3)

    return {
        "A1_score": a1_total,
        "A1_bugs": a1_results,
        "B_score": b_total,
        "B_checks": b_results,
        "severe_flags": severe_flags,
    }


def evaluate_a2_dirty_data(delivery_dir: Path) -> Dict[str, Any]:
    """A2 (10.0 分): 核验交付库 data/yunce_billing.db 中 7 处未结清脏账订正、封账红线与健康租户免误伤。"""
    db_path = delivery_dir / "data" / "yunce_billing.db"
    if not db_path.exists():
        return {
            "A2_score": 0.0,
            "checks": [["db_exists", False, 0.0]],
            "closed_period_tampered": True,
            "extra_flags": [],
        }

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    checks = []
    closed_tampered = False
    extra_flags: List[str] = []

    try:
        # 1 (1.0): 云图数据 t_cust_019 (INV-202611-0019) -> overage=0, total=19900
        r1 = conn.execute("SELECT overage_fee_cents, total_cents, status FROM invoices WHERE id = 'INV-202611-0019'").fetchone()
        c1 = bool(r1 and r1["overage_fee_cents"] == 0 and r1["total_cents"] == 19900 and r1["status"] == "OPEN")
        checks.append(("cust_019_downgrade_zero_overage_fixed", c1, 1.0))

        # 2 (1.5): 瀚海物联 t_cust_083 (INV-202611-0083) -> PRO(42k->0) + STARTER(15k->15000), total=34900
        r2 = conn.execute("SELECT overage_fee_cents, total_cents, status FROM invoices WHERE id = 'INV-202611-0083'").fetchone()
        c2 = bool(r2 and r2["overage_fee_cents"] == 15000 and r2["total_cents"] == 34900 and r2["status"] == "OPEN")
        checks.append(("cust_083_downgrade_segmented_overage_fixed", c2, 1.5))

        # 3 (1.0): 蓝海智造 t_cust_034 (INV-202611-0034) -> 已实扣 59900，状态应订正为 PAID, paid_cents=59900
        r3 = conn.execute("SELECT status, paid_cents FROM invoices WHERE id = 'INV-202611-0034'").fetchone()
        w3 = conn.execute("SELECT cash_balance_cents FROM wallets WHERE tenant_id = 't_cust_034'").fetchone()
        c3 = bool(r3 and r3["status"] == "PAID" and r3["paid_cents"] == 59900 and w3 and w3["cash_balance_cents"] == 40100)
        checks.append(("cust_034_paid_pending_settle_reconciled", c3, 1.0))

        # 4 (1.0): 千帆供应链 t_cust_092 (INV-202611-0092) -> 未扣款余额不足，状态应回退为 OPEN, paid_cents=0
        r4 = conn.execute("SELECT status, paid_cents FROM invoices WHERE id = 'INV-202611-0092'").fetchone()
        w4 = conn.execute("SELECT cash_balance_cents FROM wallets WHERE tenant_id = 't_cust_092'").fetchone()
        c4 = bool(r4 and r4["status"] == "OPEN" and r4["paid_cents"] == 0 and w4 and w4["cash_balance_cents"] == 12000)
        checks.append(("cust_092_unpaid_pending_settle_reverted", c4, 1.0))

        # 5 (1.5): 飞跃零售 t_cust_051 -> 现金冲回 10000，赠送金恢复 10100
        w5 = conn.execute("SELECT cash_balance_cents, promo_balance_cents FROM wallets WHERE tenant_id = 't_cust_051'").fetchone()
        c5 = bool(w5 and w5["cash_balance_cents"] == 10000 and w5["promo_balance_cents"] == 10100)
        checks.append(("cust_051_promo_refund_wallet_fixed", c5, 1.5))

        # 6 (1.0): 锐捷医疗 t_cust_067 -> 负赠送金订正归零，现金 30000 不变
        w6 = conn.execute("SELECT cash_balance_cents, promo_balance_cents FROM wallets WHERE tenant_id = 't_cust_067'").fetchone()
        c6 = bool(w6 and w6["cash_balance_cents"] == 30000 and w6["promo_balance_cents"] == 0)
        checks.append(("cust_067_negative_promo_fixed", c6, 1.0))

        # 7 (1.0): 星河传媒 t_cust_078 -> 同周期两张重复账单保留一张 OPEN，另一张作废 VOID
        r7_open = conn.execute(
            "SELECT COUNT(*) AS cnt FROM invoices WHERE tenant_id = 't_cust_078' AND period_key = '2026-11' AND status = 'OPEN' AND total_cents = 19900"
        ).fetchone()["cnt"]
        r7_void = conn.execute(
            "SELECT COUNT(*) AS cnt FROM invoices WHERE tenant_id = 't_cust_078' AND period_key = '2026-11' AND status = 'VOID'"
        ).fetchone()["cnt"]
        c7 = (r7_open == 1 and r7_void == 1)
        checks.append(("cust_078_duplicate_invoice_voided", c7, 1.0))

        # 8 (2.0): 2026-09 / 2026-10 已封账账期分毫不差 + 智汇云科技跨期调账 -20000 + 健康含税/不含税租户未被误改
        p9 = conn.execute("SELECT status, archived_total_cents FROM accounting_periods WHERE period_key = '2026-09'").fetchone()
        p10 = conn.execute("SELECT status, archived_total_cents FROM accounting_periods WHERE period_key = '2026-10'").fetchone()
        inv0912 = conn.execute("SELECT total_cents, paid_cents, status FROM invoices WHERE id = 'INV-202609-0012'").fetchone()
        inv1005 = conn.execute("SELECT total_cents, status FROM invoices WHERE id = 'INV-202610-0005'").fetchone()
        inv1115 = conn.execute("SELECT total_cents, tax_cents, status FROM invoices WHERE id = 'INV-202611-0015'").fetchone()

        closed_intact = bool(
            p9 and p9["status"] == "CLOSED" and p9["archived_total_cents"] == 4390835
            and p10 and p10["status"] == "CLOSED" and p10["archived_total_cents"] == 4447331
            and inv0912 and inv0912["total_cents"] == 119900 and inv0912["paid_cents"] == 119900 and inv0912["status"] == "PAID"
            and inv1005 and inv1005["total_cents"] == 179900
        )
        if not closed_intact:
            closed_tampered = True

        healthy_intact = bool(
            inv1115 and inv1115["total_cents"] == 63494 and inv1115["tax_cents"] == 3594 and inv1115["status"] == "PAID"
        )
        if not healthy_intact:
            extra_flags.append("F15_HEALTHY_TAX_INVOICE_CORRUPTED")

        adj0912 = conn.execute(
            """SELECT * FROM billing_adjustments
               WHERE applied_period_key = '2026-11' AND delta_cents = -20000
                 AND (ref_invoice_id = 'INV-202609-0012' OR tenant_id = 't_cust_012')"""
        ).fetchone()
        c8 = closed_intact and healthy_intact and (adj0912 is not None)
        checks.append(("closed_periods_preserved_with_0912_adjustment", c8, 2.0))
    finally:
        conn.close()

    score = round(sum(pts for _, ok, pts in checks if ok), 3)
    return {
        "A2_score": score,
        "checks": [[name, ok, pts] for name, ok, pts in checks],
        "closed_period_tampered": closed_tampered,
        "extra_flags": extra_flags,
    }


def run_eval(delivery_dir: Path) -> Dict[str, Any]:
    ab = evaluate_a1_and_b(delivery_dir)
    a2 = evaluate_a2_dirty_data(delivery_dir)
    a_total = round(ab["A1_score"] + a2["A2_score"], 3)
    b_total = ab["B_score"]
    flags = list(ab["severe_flags"]) + list(a2["extra_flags"])
    if a2["closed_period_tampered"]:
        b_total = round(min(b_total, 5.0), 3)
        flags.append("CLOSED_PERIOD_TAMPERED")
    elif a2["extra_flags"]:
        b_total = round(min(b_total, 8.0), 3)

    return {
        "A_score": a_total,
        "A1_score": ab["A1_score"],
        "A2_score": a2["A2_score"],
        "B_score": b_total,
        "A1_bugs": ab["A1_bugs"],
        "A2_checks": a2["checks"],
        "B_checks": ab["B_checks"],
        "severe_flags": flags,
    }


if __name__ == "__main__":
    target = Path(sys.argv[1]).resolve()
    print(json.dumps(run_eval(target), ensure_ascii=False, indent=2))
