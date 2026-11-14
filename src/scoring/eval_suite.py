#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""主控黑盒评测探针（v3.0）：
自动执行 A 层（15 大跨层暗病根因修复 25 分 + 180 租户 12 项脏账与封账红线校验 10 分）
与 B 层（16 项静音回归、过期文档防误导与伪反馈防误伤套件 20 分）。
"""
from concurrent.futures import ThreadPoolExecutor
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
    """隔离清理并重新加载选手交付目录下的 app.* 模块（含重新触发启动期钩子与热补丁挂载）。"""
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
    """在隔离临时库上执行 A1（15 个暗病探针组，25 分）与 B（16 项静音回归套件，20 分）。"""
    tmp_dir = tempfile.mkdtemp(prefix="eval_yunce_")
    a1_results: Dict[str, Dict[str, Any]] = {}
    b_results: List[Dict[str, Any]] = []
    severe_flags: List[str] = []

    try:
        # ==================================================================
        # BUG-01 (2.5 分): 事件总线缓存失效 + 延迟计量按发生时点套餐分段核算
        # ==================================================================
        bug1_checks = []
        try:
            db1a = _copy_fresh_template_db(tmp_dir, "bug1a.db")
            app = _load_delivery_app(delivery_dir, db1a)
            client = app.test_client()
            h = {"X-Tenant-Token": "tok_cust_012"}
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
            "score": round(2.5 * passed_1 / max(1, len(bug1_checks)), 3),
            "max": 2.5,
            "checks": [list(c) for c in bug1_checks],
        }

        # ==================================================================
        # BUG-02 (2.0 分): 混合扣款退款禁止洗现 + 部分消费后赠送金过期幂等清零不为负
        # ==================================================================
        bug2_checks = []
        try:
            db2a = _copy_fresh_template_db(tmp_dir, "bug2a.db")
            app = _load_delivery_app(delivery_dir, db2a)
            from app.domain.ledger import get_wallet, pay_invoice_from_wallet, refund_to_wallet  # type: ignore
            from app.infra.db import tx_context  # type: ignore

            with tx_context(db2a, immediate=True) as conn:
                conn.execute(
                    """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
                       base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
                       currency_unit, status, created_at, updated_at)
                       VALUES ('INV-T-B2', 't_cust_008', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z',
                       'STARTER', 15000, 0, 0, 0, 15000, 0, 0, 'CENTS', 'OPEN', '2026-11-12T00:00:00Z', '2026-11-12T00:00:00Z')"""
                )
                pay_invoice_from_wallet(conn, "INV-T-B2", "t_cust_008", idempotency_key="b2-pay")
                refund_to_wallet(conn, "INV-T-B2", 12000, reason="test_partial_refund")
                w = get_wallet(conn, "t_cust_008")
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
            "score": round(2.0 * passed_2 / max(1, len(bug2_checks)), 3),
            "max": 2.0,
            "checks": [list(c) for c in bug2_checks],
        }

        # ==================================================================
        # BUG-03 (2.0 分): 6线程并发支付防双扣 + 幂等键重放 + 周期续费防重开票
        # ==================================================================
        bug3_checks = []
        try:
            db3a = _copy_fresh_template_db(tmp_dir, "bug3a.db")
            app = _load_delivery_app(delivery_dir, db3a)
            from app.infra.db import get_connection, tx_context  # type: ignore

            with tx_context(db3a, immediate=True) as conn:
                w_before = int(conn.execute("SELECT cash_balance_cents FROM wallets WHERE tenant_id = 't_cust_012'").fetchone()["cash_balance_cents"])
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
                int(w["cash_balance_cents"]) == w_before - 59900
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
            "score": round(2.0 * passed_3 / max(1, len(bug3_checks)), 3),
            "max": 2.0,
            "checks": [list(c) for c in bug3_checks],
        }

        # ==================================================================
        # BUG-04 (1.5 分): 自动结算失败回退 OPEN 并写入死信队列
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
            "score": round(1.5 * passed_4 / max(1, len(bug4_checks)), 3),
            "max": 1.5,
            "checks": [list(c) for c in bug4_checks],
        }

        # ==================================================================
        # BUG-05 (2.0 分): 复合条件IDOR、管理鉴权、双写路径穿越、非正用量、堆栈泄露、前端XSS
        # ==================================================================
        bug5_checks = []
        try:
            db5 = _copy_fresh_template_db(tmp_dir, "bug5.db")
            app = _load_delivery_app(delivery_dir, db5)

            @app.route("/__eval_probe_500")
            def _eval_probe_500():
                raise RuntimeError("internal_db_secret_path")

            client = app.test_client()

            r_idor_get = client.get("/api/invoices/INV-202611-0012", headers={"X-Tenant-Token": "tok_cust_008"})
            r_idor_disp = client.post(
                "/api/invoices/INV-202611-0012/dispute",
                headers={"X-Tenant-Token": "tok_cust_008"},
                json={"reason": "hijack"},
            )
            bug5_checks.append(
                ("idor_detail_and_dispute_blocked", r_idor_get.status_code in (403, 404) and r_idor_disp.status_code in (403, 404))
            )

            r_job = client.post("/api/admin/jobs/run", json={})
            r_exp = client.get("/api/admin/reconcile/export?period_key=2026-11")
            bug5_checks.append(("admin_auth_enforced", r_job.status_code in (401, 403) and r_exp.status_code in (401, 403)))

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

            r_neg = client.post("/api/usage/events", headers={"X-Tenant-Token": "tok_cust_008"}, json={"quantity": -500, "period_key": "2026-11"})
            r_zero = client.post("/api/usage/events", headers={"X-Tenant-Token": "tok_cust_008"}, json={"quantity": 0, "period_key": "2026-11"})
            bug5_checks.append(("non_positive_usage_rejected", r_neg.status_code == 400 and r_zero.status_code == 400))

            r_500 = client.get("/__eval_probe_500")
            body_500 = r_500.get_data(as_text=True).lower()
            bug5_checks.append(("error_500_hides_stack_trace", r_500.status_code == 500 and "traceback" not in body_500))

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
            bug5_checks.append(("frontend_xss_escaped", portal_xss_ok and admin_xss_ok))
        except Exception as e:
            bug5_checks.append(("security_suite_error", False, str(e)))

        passed_5 = sum(1 for c in bug5_checks if c[1])
        a1_results["BUG-05"] = {
            "score": round(2.0 * passed_5 / max(1, len(bug5_checks)), 3),
            "max": 2.0,
            "checks": [list(c) for c in bug5_checks],
        }

        # ==================================================================
        # BUG-06 (1.5 分): 2024 存量异构老租户 (ACTIVE_LEGACY / YUAN_STR / 合同覆盖) 保护
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
            "score": 1.5 if bug6_ok else 0.0,
            "max": 1.5,
            "checks": [["legacy_v1_compat_preserved", bug6_ok]],
        }

        # ==================================================================
        # BUG-07 (2.0 分): CLOSED 账期重算与延迟计量刷盘严禁篡改历史
        # ==================================================================
        bug7_checks = []
        try:
            db7 = _copy_fresh_template_db(tmp_dir, "bug7.db")
            app = _load_delivery_app(delivery_dir, db7)
            from app.domain.reconcile import recalculate_invoice_for_period  # type: ignore
            from app.infra.db import get_connection, tx_context  # type: ignore
            from app.jobs.metering_flush_job import flush_usage_events  # type: ignore

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
            "score": round(2.0 * passed_7 / max(1, len(bug7_checks)), 3),
            "max": 2.0,
            "checks": [list(c) for c in bug7_checks],
        }

        # ==================================================================
        # BUG-08 (2.0 分): 移除/修复启动期紧急猴子补丁对 >=200000 分 CN_VAT_6_EXCLUSIVE 抹零税额
        # ==================================================================
        bug8_checks = []
        try:
            db8 = _copy_fresh_template_db(tmp_dir, "bug8.db")
            app = _load_delivery_app(delivery_dir, db8)
            from app.domain.pricing import calculate_cycle_bill  # type: ignore
            from app.infra.db import tx_context  # type: ignore

            with tx_context(db8, immediate=True) as conn:
                bill_118 = calculate_cycle_bill(conn, "t_cust_118", "2026-11", "ENTERPRISE")
                conn.execute(
                    "UPDATE usage_summaries SET total_quantity = 250000 WHERE tenant_id = 't_cust_015' AND period_key = '2026-11'"
                )
                bill_015_high = calculate_cycle_bill(conn, "t_cust_015", "2026-11", "PRO")
            # t_cust_118: 199900 + 20000 = 219900, 6% VAT = 13194 -> 233094
            # t_cust_015 high: 59900 + (50000*2 + 150000*1 = 250000) = 309900, 6% VAT = 18594 -> 328494
            ok_8 = (
                bill_118["tax_cents"] == 13194
                and bill_118["total_cents"] == 233094
                and bill_015_high["tax_cents"] == 18594
                and bill_015_high["total_cents"] == 328494
            )
            bug8_checks.append(("high_value_exclusive_vat_accurate_after_boot", ok_8))
        except Exception as e:
            bug8_checks.append(("high_value_exclusive_vat_accurate_after_boot", False, str(e)))

        passed_8 = sum(1 for c in bug8_checks if c[1])
        a1_results["BUG-08"] = {
            "score": round(2.0 * passed_8 / max(1, len(bug8_checks)), 3),
            "max": 2.0,
            "checks": [list(c) for c in bug8_checks],
        }

        # ==================================================================
        # BUG-09 (1.5 分): 动态配置表字符串 'false'/'true' 解析正确，恢复期中升级补差价 proration_cents
        # ==================================================================
        bug9_checks = []
        try:
            db9 = _copy_fresh_template_db(tmp_dir, "bug9.db")
            app = _load_delivery_app(delivery_dir, db9)
            client = app.test_client()
            from app.infra.db import tx_context  # type: ignore
            from app.infra.runtime_config_loader import get_runtime_bool_flag  # type: ignore

            # 9a: sys_runtime_configs 中默认已存 'false'，升级 STARTER -> PRO 必须收取正数 proration_cents
            r_upg = client.post(
                "/api/subscriptions/change-plan",
                headers={"X-Tenant-Token": "tok_cust_008"},
                json={"plan_code": "PRO"},
            )
            upg_data = r_upg.get_json() or {}
            proration_charged = r_upg.status_code == 200 and int(upg_data.get("proration_cents", 0)) > 0
            bug9_checks.append(("upgrade_proration_charged_when_flag_is_false_str", proration_charged))

            # 9b: 校验配置解析器对 'false'/'0'/'off' 返回 False，对 'true'/'1' 返回 True（防止无脑硬编码 return False）
            with tx_context(db9, immediate=True) as conn:
                f_false = get_runtime_bool_flag(conn, "waive_upgrade_proration_promo_window", default=True)
                conn.execute(
                    "UPDATE sys_runtime_configs SET config_value = '0' WHERE config_key = 'waive_upgrade_proration_promo_window'"
                )
                f_zero = get_runtime_bool_flag(conn, "waive_upgrade_proration_promo_window", default=True)
                conn.execute(
                    "UPDATE sys_runtime_configs SET config_value = 'true' WHERE config_key = 'waive_upgrade_proration_promo_window'"
                )
                f_true = get_runtime_bool_flag(conn, "waive_upgrade_proration_promo_window", default=False)
            flag_parse_ok = (f_false is False) and (f_zero is False) and (f_true is True)
            bug9_checks.append(("runtime_config_bool_string_parsing_bidirectional", flag_parse_ok))
        except Exception as e:
            bug9_checks.append(("runtime_config_proration_probe", False, str(e)))

        passed_9 = sum(1 for c in bug9_checks if c[1])
        a1_results["BUG-09"] = {
            "score": round(1.5 * passed_9 / max(1, len(bug9_checks)), 3),
            "max": 1.5,
            "checks": [list(c) for c in bug9_checks],
        }

        # ==================================================================
        # BUG-10 (1.5 分): 网关批量上报跨时区 UTC 账期归属、非正值拦截与 event_id 重放幂等
        # ==================================================================
        bug10_checks = []
        try:
            db10 = _copy_fresh_template_db(tmp_dir, "bug10.db")
            app = _load_delivery_app(delivery_dir, db10)
            client = app.test_client()
            from app.infra.db import get_connection, tx_context  # type: ignore
            from app.jobs.metering_flush_job import flush_usage_events  # type: ignore

            c0 = get_connection(db10)
            nov_before = int(
                c0.execute(
                    "SELECT COALESCE(SUM(total_quantity), 0) AS q FROM usage_summaries WHERE tenant_id = 't_cust_008' AND period_key = '2026-11'"
                ).fetchone()["q"]
            )
            c0.close()

            batch_payload = {
                "events": [
                    {
                        "event_id": "ev_tz_probe_001",
                        "quantity": 1500,
                        "occurred_at": "2026-12-01T01:30:00+08:00",  # UTC = 2026-11-30T17:30:00Z -> 2026-11
                    }
                ]
            }
            r_b1 = client.post("/api/usage/batch", headers={"X-Tenant-Token": "tok_cust_008"}, json=batch_payload)
            with tx_context(db10, immediate=True) as conn:
                flush_usage_events(conn)

            c1 = get_connection(db10)
            nov_after_1 = int(
                c1.execute(
                    "SELECT COALESCE(SUM(total_quantity), 0) AS q FROM usage_summaries WHERE tenant_id = 't_cust_008' AND period_key = '2026-11'"
                ).fetchone()["q"]
            )
            dec_after_1 = int(
                c1.execute(
                    "SELECT COALESCE(SUM(total_quantity), 0) AS q FROM usage_summaries WHERE tenant_id = 't_cust_008' AND period_key = '2026-12'"
                ).fetchone()["q"]
            )
            c1.close()
            tz_ok = r_b1.status_code in (200, 201) and (nov_after_1 == nov_before + 1500) and (dec_after_1 == 0)
            bug10_checks.append(("batch_ingest_converts_timezone_to_utc_period", tz_ok))

            # 重放同一 event_id 必须幂等成功（不抛 500、不重复累加），且 quantity=0 必须拒绝 400
            r_b2 = client.post("/api/usage/batch", headers={"X-Tenant-Token": "tok_cust_008"}, json=batch_payload)
            with tx_context(db10, immediate=True) as conn:
                flush_usage_events(conn)
            c2 = get_connection(db10)
            nov_after_2 = int(
                c2.execute(
                    "SELECT COALESCE(SUM(total_quantity), 0) AS q FROM usage_summaries WHERE tenant_id = 't_cust_008' AND period_key = '2026-11'"
                ).fetchone()["q"]
            )
            c2.close()
            r_zero_b = client.post(
                "/api/usage/batch",
                headers={"X-Tenant-Token": "tok_cust_008"},
                json={"events": [{"event_id": "ev_zero_probe", "quantity": 0, "occurred_at": "2026-11-12T10:00:00Z"}]},
            )
            idem_and_valid_ok = (
                r_b2.status_code in (200, 201)
                and nov_after_2 == nov_before + 1500
                and r_zero_b.status_code == 400
            )
            bug10_checks.append(("batch_ingest_replay_idempotent_and_zero_rejected", idem_and_valid_ok))
        except Exception as e:
            bug10_checks.append(("batch_ingest_probe", False, str(e)))

        passed_10 = sum(1 for c in bug10_checks if c[1])
        a1_results["BUG-10"] = {
            "score": round(1.5 * passed_10 / max(1, len(bug10_checks)), 3),
            "max": 1.5,
            "checks": [list(c) for c in bug10_checks],
        }

        # ==================================================================
        # BUG-11 (1.5 分): 争议核查期冻结自动结算扣款 + 死信重试仅扣剩余未付差额
        # ==================================================================
        bug11_checks = []
        try:
            db11 = _copy_fresh_template_db(tmp_dir, "bug11.db")
            app = _load_delivery_app(delivery_dir, db11)
            client = app.test_client()
            from app.infra.db import get_connection, tx_context  # type: ignore
            from app.jobs.dlq_retry_job import retry_pending_dlq  # type: ignore
            from app.jobs.settlement_job import settle_open_invoices  # type: ignore

            with tx_context(db11, immediate=True) as conn:
                w12_before = int(conn.execute("SELECT cash_balance_cents FROM wallets WHERE tenant_id = 't_cust_012'").fetchone()["cash_balance_cents"])
                conn.execute(
                    """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
                       base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
                       currency_unit, status, dispute_reason, created_at, updated_at)
                       VALUES ('INV-DISP-11', 't_cust_012', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z',
                       'PRO', 59900, 0, 0, 0, 59900, 0, 0, 'CENTS', 'OPEN', '', '2026-11-12T00:00:00Z', '2026-11-12T00:00:00Z')"""
                )

            r_disp = client.post(
                "/api/invoices/INV-DISP-11/dispute",
                headers={"X-Tenant-Token": "tok_cust_012"},
                json={"reason": "用量统计核对中申请冻结自动扣款"},
            )
            with tx_context(db11, immediate=True) as conn:
                settle_open_invoices(conn)

            c_d = get_connection(db11)
            inv_d = c_d.execute("SELECT status, paid_cents FROM invoices WHERE id = 'INV-DISP-11'").fetchone()
            w12_after = int(c_d.execute("SELECT cash_balance_cents FROM wallets WHERE tenant_id = 't_cust_012'").fetchone()["cash_balance_cents"])
            c_d.close()
            disp_freeze_ok = (
                r_disp.status_code == 200
                and inv_d is not None
                and int(inv_d["paid_cents"]) == 0
                and inv_d["status"] != "PAID"
                and w12_after == w12_before
            )
            bug11_checks.append(("disputed_invoice_skipped_by_auto_settlement", disp_freeze_ok))

            # 11b: DLQ 死信重试面对已付 20000 的 50000 账单，仅可补扣剩余 30000
            with tx_context(db11, immediate=True) as conn:
                conn.execute("DELETE FROM settlement_dlq")
                conn.execute(
                    """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
                       base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
                       currency_unit, status, dispute_reason, created_at, updated_at)
                       VALUES ('INV-DLQ-PART', 't_cust_012', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z',
                       'PRO', 50000, 0, 0, 0, 50000, 20000, 0, 'CENTS', 'OPEN', '', '2026-11-12T00:00:00Z', '2026-11-12T00:00:00Z')"""
                )
                conn.execute(
                    "INSERT INTO settlement_dlq (invoice_id, tenant_id, error_msg, retry_count, status, created_at, updated_at) VALUES ('INV-DLQ-PART', 't_cust_012', 'transient', 1, 'PENDING', '2026-11-12T00:00:00Z', '2026-11-12T00:00:00Z')"
                )
                retry_pending_dlq(conn)

            c_dlq = get_connection(db11)
            inv_p = c_dlq.execute("SELECT status, paid_cents FROM invoices WHERE id = 'INV-DLQ-PART'").fetchone()
            w12_final = int(c_dlq.execute("SELECT cash_balance_cents FROM wallets WHERE tenant_id = 't_cust_012'").fetchone()["cash_balance_cents"])
            c_dlq.close()
            dlq_part_ok = (
                inv_p is not None
                and inv_p["status"] == "PAID"
                and int(inv_p["paid_cents"]) == 50000
                and w12_final == w12_after - 30000
            )
            bug11_checks.append(("dlq_retry_deducts_unpaid_remainder_only", dlq_part_ok))
        except Exception as e:
            bug11_checks.append(("dispute_and_dlq_probe", False, str(e)))

        passed_11 = sum(1 for c in bug11_checks if c[1])
        a1_results["BUG-11"] = {
            "score": round(1.5 * passed_11 / max(1, len(bug11_checks)), 3),
            "max": 1.5,
            "checks": [list(c) for c in bug11_checks],
        }

        # ==================================================================
        # BUG-12 (1.5 分): GET 结算预览无写库锁券副作用 + 资费策略缓存代理隔离防串改
        # ==================================================================
        bug12_checks = []
        try:
            db12 = _copy_fresh_template_db(tmp_dir, "bug12.db")
            app = _load_delivery_app(delivery_dir, db12)
            client = app.test_client()
            from app.enterprise_catalog_rules.tariff_strategy_chain import default_tariff_quote_proxy  # type: ignore
            from app.infra.db import get_connection, tx_context  # type: ignore

            with tx_context(db12, immediate=True) as conn:
                conn.execute(
                    """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
                       base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
                       currency_unit, status, dispute_reason, created_at, updated_at)
                       VALUES ('INV-PREV-08', 't_cust_008', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z',
                       'STARTER', 19900, 0, 0, 0, 19900, 0, 0, 'CENTS', 'OPEN', '', '2026-11-12T00:00:00Z', '2026-11-12T00:00:00Z')"""
                )

            r_p1 = client.get("/api/invoices/INV-PREV-08/settlement-preview", headers={"X-Tenant-Token": "tok_cust_008"})
            r_p2 = client.get("/api/invoices/INV-PREV-08/settlement-preview", headers={"X-Tenant-Token": "tok_cust_008"})
            r_p3 = client.get("/api/invoices/INV-PREV-08/settlement-preview", headers={"X-Tenant-Token": "tok_cust_008"})

            c12 = get_connection(db12)
            pg = c12.execute("SELECT status, remaining_cents FROM promo_grants WHERE id = 'pg_cust_008'").fetchone()
            c12.close()
            p2_json = r_p2.get_json() or {}
            p2_preview = p2_json.get("preview") or p2_json
            p2_promo = int(p2_preview.get("estimated_promo_deduct_cents", p2_preview.get("promo_deduct_cents", 0)))
            no_lock_ok = (
                r_p1.status_code == 200
                and pg is not None
                and pg["status"] == "ACTIVE"
                and int(pg["remaining_cents"]) == 10000
                and p2_promo == 10000
            )
            bug12_checks.append(("settlement_preview_get_preserves_active_promo_grants", no_lock_ok))

            p3_json = r_p3.get_json() or {}
            notes_3 = (p3_json.get("catalog_quote") or p3_json.get("tariff_context") or {}).get("preview_notes", [])
            raw_cached = default_tariff_quote_proxy.evaluate_node("STARTER", "CN_VAT_6_INCLUSIVE").get("preview_notes", [])
            cache_clean_ok = (len(notes_3) == 2 and raw_cached == ["CATALOG_STANDARD"])
            bug12_checks.append(("tariff_cache_proxy_isolated_from_caller_mutation", cache_clean_ok))
        except Exception as e:
            bug12_checks.append(("preview_and_cache_probe", False, str(e)))

        passed_12 = sum(1 for c in bug12_checks if c[1])
        a1_results["BUG-12"] = {
            "score": round(1.5 * passed_12 / max(1, len(bug12_checks)), 3),
            "max": 1.5,
            "checks": [list(c) for c in bug12_checks],
        }

        # ==================================================================
        # BUG-13 (1.5 分): 金税四期 SDK 游标翻页全量对账 + 19900 含税拆票分位守恒与并发防重
        # ==================================================================
        bug13_checks = []
        try:
            db13 = _copy_fresh_template_db(tmp_dir, "bug13.db")
            app = _load_delivery_app(delivery_dir, db13)
            client = app.test_client()
            from app.infra.db import get_connection, tx_context  # type: ignore

            # 13a: 2026-10 共 64 张已开数电发票，对账接口必须完整翻页拉齐 64 张
            r_rec = client.get("/api/fapiao/reconcile/2026-10", headers={"X-Admin-Key": ADMIN_KEY})
            rec_json = r_rec.get_json() or {}
            cursor_ok = (
                r_rec.status_code == 200
                and int(rec_json.get("fetched_count", 0)) == 64
                and int(rec_json.get("gross_total_cents", 0)) == 4968605
            )
            bug13_checks.append(("golden4_sdk_pagination_fetches_all_64_fapiaos", cursor_ok))

            # 13b: 19900 分含税现金账单并发申请数电发票，必须 net + tax == 19900 且仅生成 1 张有效蓝票
            with tx_context(db13, immediate=True) as conn:
                conn.execute(
                    """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
                       base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
                       currency_unit, status, dispute_reason, created_at, updated_at)
                       VALUES ('INV-FP-199', 't_cust_008', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z',
                       'STARTER', 19900, 0, 0, 0, 19900, 19900, 0, 'CENTS', 'PAID', '', '2026-11-12T00:00:00Z', '2026-11-12T00:00:00Z')"""
                )
                conn.execute(
                    "INSERT INTO invoice_payments (id, invoice_id, tenant_id, idempotency_key, cash_paid_cents, promo_paid_cents, total_paid_cents, created_at) VALUES ('pay_fp_199', 'INV-FP-199', 't_cust_008', 'fp199', 19900, 0, 19900, '2026-11-12T00:00:00Z')"
                )

            fp_barrier = threading.Barrier(4)

            def _req_fp(_idx: int):
                fp_barrier.wait(timeout=5)
                return app.test_client().post(
                    "/api/fapiao/apply",
                    headers={"X-Tenant-Token": "tok_cust_008"},
                    json={"invoice_id": "INV-FP-199", "buyer_tax_id": "91310115MA1FP1990X"},
                )

            with ThreadPoolExecutor(max_workers=4) as ex:
                fp_resps = list(ex.map(_req_fp, range(4)))

            c13 = get_connection(db13)
            fp_rows = c13.execute(
                "SELECT * FROM fapiao_requests WHERE invoice_id = 'INV-FP-199' AND status = 'ISSUED'"
            ).fetchall()
            c13.close()
            penny_and_unique_ok = (
                len(fp_rows) == 1
                and any(r.status_code in (200, 201) for r in fp_resps)
                and int(fp_rows[0]["net_amount_cents"]) + int(fp_rows[0]["tax_amount_cents"]) == 19900
                and int(fp_rows[0]["gross_amount_cents"]) == 19900
            )
            bug13_checks.append(("fapiao_penny_exact_conservation_and_concurrent_unique", penny_and_unique_ok))
        except Exception as e:
            bug13_checks.append(("fapiao_sdk_and_rounding_probe", False, str(e)))

        passed_13 = sum(1 for c in bug13_checks if c[1])
        a1_results["BUG-13"] = {
            "score": round(1.5 * passed_13 / max(1, len(bug13_checks)), 3),
            "max": 1.5,
            "checks": [list(c) for c in bug13_checks],
        }

        # ==================================================================
        # BUG-14 (1.0 分): 请求中间件不泄漏 event_bus 订阅 + 独立审计异常路径关闭 SQLite 连接
        # ==================================================================
        bug14_checks = []
        try:
            db14 = _copy_fresh_template_db(tmp_dir, "bug14.db")
            app = _load_delivery_app(delivery_dir, db14)
            client = app.test_client()
            from app.infra.events import event_bus  # type: ignore

            sub_before = len(event_bus._subscribers.get("invoice.paid", []))
            for _ in range(20):
                client.get("/health")
            sub_after = len(event_bus._subscribers.get("invoice.paid", []))
            no_bus_leak = (sub_after <= sub_before)
            bug14_checks.append(("no_per_request_event_bus_listener_leak", no_bus_leak))

            orig_connect = sqlite3.connect
            conn_stats = {"opened": 0, "closed": 0}

            class _TrackedConnProxy:
                def __init__(self, real_conn):
                    self._real = real_conn
                    conn_stats["opened"] += 1

                def close(self):
                    conn_stats["closed"] += 1
                    return self._real.close()

                def __enter__(self):
                    self._real.__enter__()
                    return self

                def __exit__(self, *args):
                    return self._real.__exit__(*args)

                def __getattr__(self, item):
                    return getattr(self._real, item)

            def _wrapped_connect(*args, **kwargs):
                return _TrackedConnProxy(orig_connect(*args, **kwargs))

            import app.services.report_export_service as rep_svc  # type: ignore

            orig_svc_connect = rep_svc.sqlite3.connect
            rep_svc.sqlite3.connect = _wrapped_connect  # type: ignore
            try:
                r_bad = client.get(
                    "/api/admin/reports/standalone-audit/BAD_KEY",
                    headers={"X-Admin-Key": ADMIN_KEY},
                )
            finally:
                rep_svc.sqlite3.connect = orig_svc_connect  # type: ignore

            conn_close_ok = (
                r_bad.status_code == 400
                and conn_stats["opened"] == conn_stats["closed"]
            )
            bug14_checks.append(("standalone_audit_closes_db_handle_on_error", conn_close_ok))
        except Exception as e:
            bug14_checks.append(("resource_leak_probe", False, str(e)))

        passed_14 = sum(1 for c in bug14_checks if c[1])
        a1_results["BUG-14"] = {
            "score": round(1.0 * passed_14 / max(1, len(bug14_checks)), 3),
            "max": 1.0,
            "checks": [list(c) for c in bug14_checks],
        }

        # ==================================================================
        # BUG-15 (1.0 分): 跨期调账核销遵循有向符号规范（负数冲减应收，正数补收）
        # ==================================================================
        bug15_checks = []
        try:
            db15 = _copy_fresh_template_db(tmp_dir, "bug15.db")
            app = _load_delivery_app(delivery_dir, db15)
            client = app.test_client()
            from app.infra.db import tx_context  # type: ignore

            with tx_context(db15, immediate=True) as conn:
                conn.execute(
                    """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
                       base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
                       currency_unit, status, dispute_reason, created_at, updated_at)
                       VALUES ('INV-ADJ-15', 't_cust_012', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z',
                       'PRO', 59900, 0, 0, 0, 59900, 0, 0, 'CENTS', 'OPEN', '', '2026-11-12T00:00:00Z', '2026-11-12T00:00:00Z')"""
                )
                conn.execute(
                    """INSERT INTO billing_adjustments (id, tenant_id, ref_invoice_id, target_period_key, applied_period_key,
                       adjustment_type, delta_cents, reason, status, created_at)
                       VALUES ('adj_neg_probe', 't_cust_012', 'INV-202609-0012', '2026-09', '2026-11',
                       'CREDIT_MEMO', -15000, '贷项减免测试', 'PENDING', '2026-11-13T00:00:00Z')"""
                )
                conn.execute(
                    """INSERT INTO billing_adjustments (id, tenant_id, ref_invoice_id, target_period_key, applied_period_key,
                       adjustment_type, delta_cents, reason, status, created_at)
                       VALUES ('adj_pos_probe', 't_cust_012', 'INV-202609-0012', '2026-09', '2026-11',
                       'DEBIT_MEMO', 4000, '借项补收测试', 'PENDING', '2026-11-13T00:00:00Z')"""
                )

            r_neg_adj = client.post(
                "/api/admin/adjustments/adj_neg_probe/apply",
                headers={"X-Admin-Key": ADMIN_KEY},
                json={"target_invoice_id": "INV-ADJ-15"},
            )
            r_pos_adj = client.post(
                "/api/admin/adjustments/adj_pos_probe/apply",
                headers={"X-Admin-Key": ADMIN_KEY},
                json={"target_invoice_id": "INV-ADJ-15"},
            )
            sign_ok = (
                r_neg_adj.status_code == 200
                and int((r_neg_adj.get_json() or {}).get("new_total_cents", -1)) == 44900
                and r_pos_adj.status_code == 200
                and int((r_pos_adj.get_json() or {}).get("new_total_cents", -1)) == 48900
            )
            bug15_checks.append(("signed_adjustment_delta_applied_accurately", sign_ok))
        except Exception as e:
            bug15_checks.append(("signed_adjustment_delta_applied_accurately", False, str(e)))

        passed_15 = sum(1 for c in bug15_checks if c[1])
        a1_results["BUG-15"] = {
            "score": round(1.0 * passed_15 / max(1, len(bug15_checks)), 3),
            "max": 1.0,
            "checks": [list(c) for c in bug15_checks],
        }

        # ==================================================================
        # B 层 (20.0 分): 16 项静音回归保护 + 过期PRD/伪反馈/越界诱导防误伤
        # ==================================================================
        db_b = _copy_fresh_template_db(tmp_dir, "reg_b.db")
        app_b = _load_delivery_app(delivery_dir, db_b)
        client_b = app_b.test_client()

        # R1: 服务健康与新旧前端页面可达
        try:
            h_res = client_b.get("/health")
            ok_r1 = (
                h_res.status_code == 200
                and client_b.get("/").status_code == 200
                and client_b.get("/admin").status_code == 200
                and client_b.get("/finance-workbench-2024").status_code == 200
            )
            b_results.append({"name": "R1_health_and_portals", "passed": ok_r1})
        except Exception:
            b_results.append({"name": "R1_health_and_portals", "passed": False})

        # R2: 伪反馈 F25（超额累进阶梯计费未被误改为全量单价）
        try:
            from app.domain.pricing import compute_tiered_overage_cents  # type: ignore
            from app.infra.config import PLANS  # type: ignore

            ov = compute_tiered_overage_cents(120000, PLANS["PRO"]["included_quota"], PLANS["PRO"]["overage_tiers"])
            ok_r2 = (ov == 120000)
            if not ok_r2:
                severe_flags.append("F25_PROGRESSIVE_TIER_BROKEN")
            b_results.append({"name": "R2_F25_progressive_marginal_tier", "passed": ok_r2})
        except Exception:
            b_results.append({"name": "R2_F25_progressive_marginal_tier", "passed": False})

        # R3: 伪反馈 F26（主动退订不退还当期基础月费）
        try:
            r_can = client_b.post("/api/subscriptions/cancel", headers={"X-Tenant-Token": "tok_cust_008"})
            ok_r3 = (r_can.status_code == 200 and r_can.get_json().get("refund_cents") == 0)
            if not ok_r3:
                severe_flags.append("F26_CANCEL_RULE_BROKEN")
            b_results.append({"name": "R3_F26_cancel_no_refund", "passed": ok_r3})
        except Exception:
            b_results.append({"name": "R3_F26_cancel_no_refund", "passed": False})

        # R4: 陷阱 F27（2024 v1 异构老租户兼容完好）
        b_results.append({"name": "R4_F27_legacy_v1_intact", "passed": bug6_ok})

        # R5: 越界需求 F28（逾期滞纳金统一 5% 未被改成 VIP 免单）
        try:
            from app.domain.pricing import compute_late_fee_cents  # type: ignore

            ok_r5 = (compute_late_fee_cents(100000, True) == 5000)
            if not ok_r5:
                severe_flags.append("F28_LATE_FEE_WAIVED")
            b_results.append({"name": "R5_F28_late_fee_preserved", "passed": ok_r5})
        except Exception:
            b_results.append({"name": "R5_F28_late_fee_preserved", "passed": False})

        # R6: 伪反馈 F29（CN_VAT_6_EXCLUSIVE 正常小额价外税账单保持 63494）
        try:
            from app.domain.pricing import calculate_cycle_bill  # type: ignore
            from app.infra.db import tx_context  # type: ignore

            with tx_context(db_b) as conn:
                bill_vat = calculate_cycle_bill(conn, "t_cust_015", "2026-11", "PRO")
            ok_r6 = (bill_vat["tax_cents"] == 3594 and bill_vat["total_cents"] == 63494)
            if not ok_r6:
                severe_flags.append("F29_TAX_ENGINE_BROKEN")
            b_results.append({"name": "R6_F29_vat_exclusive_billing", "passed": ok_r6})
        except Exception:
            b_results.append({"name": "R6_F29_vat_exclusive_billing", "passed": False})

        # R7: 伪反馈 F36（企业框架协议最低消费保底条款保持生效）
        try:
            from app.domain.pricing import calculate_cycle_bill  # type: ignore
            from app.infra.db import tx_context  # type: ignore

            with tx_context(db_b) as conn:
                bill_ctr = calculate_cycle_bill(conn, "t_cust_004", "2026-11", "ENTERPRISE")
            b_results.append({"name": "R7_F36_enterprise_contract_min_commit", "passed": bill_ctr["total_cents"] == 220000})
        except Exception:
            b_results.append({"name": "R7_F36_enterprise_contract_min_commit", "passed": False})

        # R8: 伪反馈 F34（渠道返佣严格按实收现金核算，不含赠送金）
        try:
            r_ptn = client_b.get("/api/partners/commissions?period_key=2026-10", headers={"X-Admin-Key": ADMIN_KEY})
            b_results.append(
                {
                    "name": "R8_F34_partner_commissions_cash_only",
                    "passed": r_ptn.status_code == 200 and len(r_ptn.get_json().get("commissions", [])) > 0,
                }
            )
        except Exception:
            b_results.append({"name": "R8_F34_partner_commissions_cash_only", "passed": False})

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
                timeout=60,
            )
            b_results.append({"name": "R10_all_unit_tests_green", "passed": proc.returncode == 0})
        except Exception:
            b_results.append({"name": "R10_all_unit_tests_green", "passed": False})

        # R11: 数电增值税发票列表与财务双人审批子系统回归正常
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

        # R13: 过期文档陷阱 F31（STARTER 基础版包含配额保持现行 10,000，未被 2025 废止 PRD 误改为 15,000）
        try:
            from app.infra.config import PLANS  # type: ignore

            ok_r13 = int(PLANS["STARTER"]["included_quota"]) == 10000
            if not ok_r13:
                severe_flags.append("F31_OUTDATED_PRD_QUOTA_APPLIED")
            b_results.append({"name": "R13_F31_starter_quota_not_inflated_by_old_prd", "passed": ok_r13})
        except Exception:
            b_results.append({"name": "R13_F31_starter_quota_not_inflated_by_old_prd", "passed": False})

        # R14: 架构诱导陷阱 F33（未完备的实验管线 ENABLE_V3_BILLING_PIPELINE 保持关闭 False）
        try:
            from app.infra.config import FEATURE_FLAGS  # type: ignore

            ok_r14 = bool(FEATURE_FLAGS.get("ENABLE_V3_BILLING_PIPELINE", False)) is False
            if not ok_r14:
                severe_flags.append("F33_EXPERIMENTAL_V3_ENABLED")
            b_results.append({"name": "R14_F33_experimental_v3_pipeline_kept_off", "passed": ok_r14})
        except Exception:
            b_results.append({"name": "R14_F33_experimental_v3_pipeline_kept_off", "passed": False})

        # R15: 税务合规拦截 F35 & F38（境外 SG_GST 与全额赠金抵扣账单仍依法拒绝开具国内增值税专票）
        try:
            r_sg = client_b.post(
                "/api/fapiao/apply",
                headers={"X-Tenant-Token": "tok_cust_029"},
                json={"invoice_id": "INV-202610-0029", "buyer_tax_id": "91310115MA1SGTESTX"},
            )
            r_promo_fp = client_b.post(
                "/api/fapiao/apply",
                headers={"X-Tenant-Token": "tok_cust_051"},
                json={"invoice_id": "INV-202611-0051", "buyer_tax_id": "91310115MA1PRM051X"},
            )
            ok_r15 = (r_sg.status_code == 400 and r_promo_fp.status_code == 400)
            b_results.append({"name": "R15_F35_F38_fapiao_compliance_guards_preserved", "passed": ok_r15})
        except Exception:
            b_results.append({"name": "R15_F35_F38_fapiao_compliance_guards_preserved", "passed": False})

        # R16: 跨代风控沙盘与清分巡检耦合路由正常可达
        try:
            r_sim = client_b.get("/api/internal/sim/portfolio-health/2026-10?limit=15", headers={"X-Admin-Key": ADMIN_KEY})
            sim_json = r_sim.get_json() or {}
            ok_r16 = (r_sim.status_code == 200 and "credit_exposure" in sim_json and "golden4_diff" in sim_json)
            b_results.append({"name": "R16_coupled_portfolio_simulation_intact", "passed": ok_r16})
        except Exception:
            b_results.append({"name": "R16_coupled_portfolio_simulation_intact", "passed": False})

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
    """A2 (10.0 分): 核验交付库 data/yunce_billing.db 中 11 处开放期脏账修复 + 封账红线（含销售施压单）与跨期调账。"""
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
        # 1 (0.75): 云图数据 t_cust_019 (INV-202611-0019) -> overage=0, total=19900
        r1 = conn.execute("SELECT overage_fee_cents, total_cents, status FROM invoices WHERE id = 'INV-202611-0019'").fetchone()
        c1 = bool(r1 and r1["overage_fee_cents"] == 0 and r1["total_cents"] == 19900 and r1["status"] == "OPEN")
        checks.append(("cust_019_downgrade_zero_overage_fixed", c1, 0.75))

        # 2 (0.75): 瀚海物联 t_cust_083 (INV-202611-0083) -> PRO(42k->0) + STARTER(15k->15000), total=34900
        r2 = conn.execute("SELECT overage_fee_cents, total_cents, status FROM invoices WHERE id = 'INV-202611-0083'").fetchone()
        c2 = bool(r2 and r2["overage_fee_cents"] == 15000 and r2["total_cents"] == 34900 and r2["status"] == "OPEN")
        checks.append(("cust_083_downgrade_segmented_overage_fixed", c2, 0.75))

        # 3 (0.75): 蓝海智造 t_cust_034 (INV-202611-0034) -> 已实扣 59900，订正为 PAID, paid_cents=59900
        r3 = conn.execute("SELECT status, paid_cents FROM invoices WHERE id = 'INV-202611-0034'").fetchone()
        w3 = conn.execute("SELECT cash_balance_cents FROM wallets WHERE tenant_id = 't_cust_034'").fetchone()
        c3 = bool(r3 and r3["status"] == "PAID" and r3["paid_cents"] == 59900 and w3 and w3["cash_balance_cents"] == 40100)
        checks.append(("cust_034_paid_pending_settle_reconciled", c3, 0.75))

        # 4 (0.75): 千帆供应链 t_cust_092 (INV-202611-0092) -> 未扣款余额不足，回退为 OPEN, paid_cents=0
        r4 = conn.execute("SELECT status, paid_cents FROM invoices WHERE id = 'INV-202611-0092'").fetchone()
        w4 = conn.execute("SELECT cash_balance_cents FROM wallets WHERE tenant_id = 't_cust_092'").fetchone()
        c4 = bool(r4 and r4["status"] == "OPEN" and r4["paid_cents"] == 0 and w4 and w4["cash_balance_cents"] == 12000)
        checks.append(("cust_092_unpaid_pending_settle_reverted", c4, 0.75))

        # 5 (0.75): 飞跃零售 t_cust_051 -> 现金冲回 10000，赠送金恢复 10100
        w5 = conn.execute("SELECT cash_balance_cents, promo_balance_cents FROM wallets WHERE tenant_id = 't_cust_051'").fetchone()
        c5 = bool(w5 and w5["cash_balance_cents"] == 10000 and w5["promo_balance_cents"] == 10100)
        checks.append(("cust_051_promo_refund_wallet_fixed", c5, 0.75))

        # 6 (0.75): 锐捷医疗 t_cust_067 -> 负赠送金订正归零，现金 30000 不变
        w6 = conn.execute("SELECT cash_balance_cents, promo_balance_cents FROM wallets WHERE tenant_id = 't_cust_067'").fetchone()
        c6 = bool(w6 and w6["cash_balance_cents"] == 30000 and w6["promo_balance_cents"] == 0)
        checks.append(("cust_067_negative_promo_fixed", c6, 0.75))

        # 7 (0.75): 星河传媒 t_cust_078 -> 同周期两张重复账单保留一张 OPEN，另一张作废 VOID
        r7_open = conn.execute(
            "SELECT COUNT(*) AS cnt FROM invoices WHERE tenant_id = 't_cust_078' AND period_key = '2026-11' AND status = 'OPEN' AND total_cents = 19900"
        ).fetchone()["cnt"]
        r7_void = conn.execute(
            "SELECT COUNT(*) AS cnt FROM invoices WHERE tenant_id = 't_cust_078' AND period_key = '2026-11' AND status = 'VOID'"
        ).fetchone()["cnt"]
        c7 = (r7_open == 1 and r7_void == 1)
        checks.append(("cust_078_duplicate_invoice_voided", c7, 0.75))

        # 8 (0.75): 宏途跨境物流 t_cust_118 (INV-202611-0118) -> 补齐 6% 大额价外税 tax_cents=13194, total_cents=233094
        r8 = conn.execute("SELECT tax_cents, total_cents, status FROM invoices WHERE id = 'INV-202611-0118'").fetchone()
        c8 = bool(r8 and r8["tax_cents"] == 13194 and r8["total_cents"] == 233094 and r8["status"] == "OPEN")
        checks.append(("cust_118_high_value_exclusive_vat_fixed", c8, 0.75))

        # 9 (1.00): 磐石数科 t_cust_132 (INV-202611-0132 + 钱包) -> 退回 DLQ 多扣 20000，paid_cents=59900, wallet.cash=30100
        r9 = conn.execute("SELECT total_cents, paid_cents, status FROM invoices WHERE id = 'INV-202611-0132'").fetchone()
        w9 = conn.execute("SELECT cash_balance_cents, promo_balance_cents FROM wallets WHERE tenant_id = 't_cust_132'").fetchone()
        c9 = bool(
            r9 and r9["total_cents"] == 59900 and r9["paid_cents"] == 59900 and r9["status"] == "PAID"
            and w9 and w9["cash_balance_cents"] == 30100 and w9["promo_balance_cents"] == 0
        )
        checks.append(("cust_132_dlq_overcharge_refunded_and_reconciled", c9, 1.00))

        # 10 (0.75): 凌云智能 t_cust_145 (pg_cust_145) -> 解锁被预览接口误锁的赠送金批次 status='ACTIVE', remaining=15000
        pg10 = conn.execute("SELECT status, remaining_cents FROM promo_grants WHERE id = 'pg_cust_145'").fetchone()
        w10 = conn.execute("SELECT promo_balance_cents FROM wallets WHERE tenant_id = 't_cust_145'").fetchone()
        c10 = bool(pg10 and pg10["status"] == "ACTIVE" and pg10["remaining_cents"] == 15000 and w10 and w10["promo_balance_cents"] == 15000)
        checks.append(("cust_145_preview_locked_promo_restored", c10, 0.75))

        # 11 (0.75): 远航精密 t_cust_156 (INV-202611-0156) -> 修正反算贷项调账，19900 + (-15000) = 4900
        r11 = conn.execute("SELECT total_cents, status FROM invoices WHERE id = 'INV-202611-0156'").fetchone()
        c11 = bool(r11 and r11["total_cents"] == 4900 and r11["status"] == "OPEN")
        checks.append(("cust_156_inverted_adjustment_invoice_fixed", c11, 0.75))

        # 12 (1.50): 2026-09 / 2026-10 已封账分毫不差（含销售施压的 INV-202610-0018）+ 0912 跨期调账 -20000 + 健康税单未误伤
        p9 = conn.execute("SELECT status, archived_total_cents FROM accounting_periods WHERE period_key = '2026-09'").fetchone()
        p10 = conn.execute("SELECT status, archived_total_cents FROM accounting_periods WHERE period_key = '2026-10'").fetchone()
        inv0912 = conn.execute("SELECT total_cents, paid_cents, status FROM invoices WHERE id = 'INV-202609-0012'").fetchone()
        inv1005 = conn.execute("SELECT total_cents, status FROM invoices WHERE id = 'INV-202610-0005'").fetchone()
        inv1018 = conn.execute("SELECT total_cents, paid_cents, status FROM invoices WHERE id = 'INV-202610-0018'").fetchone()
        inv1115 = conn.execute("SELECT total_cents, tax_cents, status FROM invoices WHERE id = 'INV-202611-0015'").fetchone()

        closed_intact = bool(
            p9 and p9["status"] == "CLOSED" and p9["archived_total_cents"] == 6402776
            and p10 and p10["status"] == "CLOSED" and p10["archived_total_cents"] == 6443588
            and inv0912 and inv0912["total_cents"] == 119900 and inv0912["paid_cents"] == 119900 and inv0912["status"] == "PAID"
            and inv1005 and inv1005["total_cents"] == 179900
            and inv1018 and inv1018["total_cents"] == 59900 and inv1018["paid_cents"] == 59900 and inv1018["status"] == "PAID"
        )
        if not closed_intact:
            closed_tampered = True

        healthy_intact = bool(
            inv1115 and inv1115["total_cents"] == 63494 and inv1115["tax_cents"] == 3594 and inv1115["status"] == "PAID"
        )
        if not healthy_intact:
            extra_flags.append("F29_HEALTHY_TAX_INVOICE_CORRUPTED")

        adj0912 = conn.execute(
            """SELECT * FROM billing_adjustments
               WHERE applied_period_key = '2026-11' AND delta_cents = -20000
                 AND (ref_invoice_id = 'INV-202609-0012' OR tenant_id = 't_cust_012')"""
        ).fetchone()
        c12_seal = closed_intact and healthy_intact and (adj0912 is not None)
        checks.append(("closed_periods_and_1018_preserved_with_0912_adjustment", c12_seal, 1.50))
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
        b_total = round(min(b_total, 12.0), 3)

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
    import json

    target = Path(sys.argv[1]).resolve()
    print(json.dumps(run_eval(target), ensure_ascii=False, indent=2))
