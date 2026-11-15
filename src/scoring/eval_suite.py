#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""主控黑盒评测探针（v4.0 地狱级深水区屎山基准）：
自动执行：
1) A1（25.0 分）：60 个独立根因暗病单元（BUG-01..BUG-60），单题严格 All-or-Nothing 全闭环计分；
2) A2（10.0 分）：240 家租户 / 34 张表 48 项无剧透开放期跨表脏账、子账本平账与历史封账字节级校验；
3) B （20.0 分）：24 项高迷惑性防诱导、过期文档定力与跨代子系统静音回归矩阵（每挂 1 项扣 2.5 分，触碰高压红线乘 0.65 全局系数）。
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATE_DB = ROOT / "src" / "legacy_template" / "data" / "yunce_billing.db"
CONFIG_PATH = ROOT / "configs" / "benchmark.json"
ADMIN_KEY = "yc-admin-secret-2026"


def _load_bug_weights() -> Dict[str, float]:
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    target_total = float(cfg.get("weights", {}).get("A1_bugs", 25.0))
    raw = {
        b["id"]: float(b["points"]) * (1.3 if b.get("silent") else 1.0)
        for b in cfg["bugs"]
    }
    raw_sum = sum(raw.values()) or 1.0
    scale = target_total / raw_sum
    return {bid: round(pts * scale, 6) for bid, pts in raw.items()}


def _copy_fresh_template_db(tmp_dir: str, name: str) -> str:
    dst = os.path.join(tmp_dir, name)
    shutil.copy2(TEMPLATE_DB, dst)
    return dst


def _load_delivery_app(delivery_dir: Path, db_path: str):
    """隔离清理并重新加载交付目录下的 app.* 模块（重新触发启动期钩子与紧急热补丁）。"""
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


def _record_bug(
    a1_results: Dict[str, Dict[str, Any]],
    weights: Dict[str, float],
    bug_id: str,
    checks: List[Tuple[Any, ...]],
) -> None:
    """单题严格 All-or-Nothing：所有子断言全部 True 方可得满分，漏修任一分支得 0 分。"""
    pts = weights[bug_id]
    all_ok = len(checks) > 0 and all(bool(c[1]) for c in checks)
    a1_results[bug_id] = {
        "score": round(pts if all_ok else 0.0, 6),
        "max": pts,
        "all_passed": all_ok,
        "checks": [list(c) for c in checks],
    }


def _run_frontend_js_probes(delivery_dir: Path) -> Dict[str, Any]:
    """在 Node ES Module 环境中对 static/js/ 下的真实前端视图组件执行 BUG-57..BUG-60 探针。"""
    js_root = (delivery_dir / "static" / "js").resolve().as_posix()
    script = f"""
import {{ fmtYuan, escapeHtml }} from "file://{js_root}/fmt.js";
import {{ computeInvoiceRemainingDueCents, renderInvoiceRows, renderWalletLedgerRows }} from "file://{js_root}/views/invoice_table.js";
import {{ renderTenantDirectoryRows }} from "file://{js_root}/views/tenant_grid.js";
import {{ renderApprovalTicketRows }} from "file://{js_root}/views/approval_drawer.js";
import {{ renderDunningCaseRows }} from "file://{js_root}/views/dunning_drawer.js";
import {{ previewFapiaoSplitsClientSide }} from "file://{js_root}/views/fapiao_split_preview.js";
import {{ buildAdjustmentSubmitPayload }} from "file://{js_root}/views/reconcile_modal.js";

const out = {{}};

// BUG-57: 四处活跃视图 XSS 转义
const xssPayload = '<img src=x onerror="window.__xss=1">';
const invHtml = renderInvoiceRows([{{
  id: "INV-XSS-1", period_key: "2026-11", plan_code: "PRO",
  base_fee_cents: 59900, overage_fee_cents: 0, tax_cents: 0,
  total_cents: 59900, paid_cents: 0, status: "OPEN",
  dispute_reason: xssPayload
}}]);
const ledHtml = renderWalletLedgerRows([{{
  created_at: "2026-11-12T00:00:00Z", entry_type: "REFUND",
  cash_delta_cents: 100, promo_delta_cents: 0, ref_id: "INV-1", note: xssPayload
}}]);
const tenHtml = renderTenantDirectoryRows([{{
  id: "t_xss", company_name: xssPayload, status: "ACTIVE",
  schema_version: 2, tax_profile_code: "EXEMPT", plan_code: "PRO",
  cash_balance_cents: 0, promo_balance_cents: 0
}}]);
const apvHtml = renderApprovalTicketRows([{{
  id: "apv_1", ticket_type: "REFUND", tenant_id: "t_1",
  amount_cents: 600000, requested_by: "alice", reason: xssPayload,
  first_approver: "bob", second_approver: null, required_approvals: 2,
  status: "FIRST_APPROVED", created_at: "2026-11-12T00:00:00Z"
}}]);
const dunContainer = {{ innerHTML: "" }};
renderDunningCaseRows(dunContainer, [{{
  invoice_id: "INV-D1", tenant_id: "t_1", company_name: xssPayload,
  stage: "SUSPENDED", overdue_days: 35, unpaid_cents: 59900, estimated_late_fee_cents: 2995
}}]);
out.bug57_invoice_ledger_escaped = !invHtml.includes("<img") && !ledHtml.includes("<img") && invHtml.includes("&lt;img");
out.bug57_tenant_approval_dunning_escaped = !tenHtml.includes("<img") && !apvHtml.includes("<img") && !dunContainer.innerHTML.includes("<img");

// BUG-58: 整数分转元精度、负号前置与部分付款剩余待付额
const y1999 = fmtYuan(1999);
const yNeg = fmtYuan(-15000);
const yZero = fmtYuan(0);
out.bug58_fmt_yuan_exact_and_negative = (y1999 === "¥19.99" && yNeg === "-¥150.00" && yZero === "¥0.00");
const remPartial = computeInvoiceRemainingDueCents({{ status: "OPEN", total_cents: 59900, paid_cents: 20000 }});
const remPaid = computeInvoiceRemainingDueCents({{ status: "PAID", total_cents: 59900, paid_cents: 59900 }});
out.bug58_remaining_due_subtracts_paid = (remPartial === 39900 && remPaid === 0);

// BUG-59: 前端数电拆票预览扣除赠送金抵扣额且价税分位守恒
const sp1 = previewFapiaoSplitsClientSide(19900, 4900, 600);
const sp2 = previewFapiaoSplitsClientSide(19900, 19900, 600);
const sp1Ok = Array.isArray(sp1) && sp1.length === 1 && sp1[0].grossCents === 15000 && (sp1[0].netCents + sp1[0].taxCents === 15000);
const sp2Ok = Array.isArray(sp2) && sp2.length === 0;
const spWhale = previewFapiaoSplitsClientSide(12019900, 200000, 600);
const whaleGross = Array.isArray(spWhale) ? spWhale.reduce((a, b) => a + b.grossCents, 0) : -1;
const whaleConserved = Array.isArray(spWhale) && spWhale.every((s) => s.netCents + s.taxCents === s.grossCents);
out.bug59_deducts_promo_and_zero_when_full_promo = Boolean(sp1Ok && sp2Ok);
out.bug59_penny_conserved_across_sheets = Boolean(whaleGross === 11819900 && whaleConserved);

// BUG-60: FIRST_APPROVED 二签按钮可操作 & 调账弹窗保留贷项负号
const apvBtnHtml = renderApprovalTicketRows([{{
  id: "apv_second", ticket_type: "LARGE_REFUND_CHECK", tenant_id: "t_cust_015",
  amount_cents: 620000, requested_by: "cs_lead", reason: "二签工单",
  first_approver: "fin_mgr", second_approver: null, required_approvals: 2,
  status: "FIRST_APPROVED", created_at: "2026-11-12T00:00:00Z"
}}]);
const doneBtnHtml = renderApprovalTicketRows([{{
  id: "apv_done", ticket_type: "LARGE_REFUND_CHECK", tenant_id: "t_cust_015",
  amount_cents: 620000, requested_by: "cs_lead", reason: "已终审",
  first_approver: "fin_mgr", second_approver: "cfo_dir", required_approvals: 2,
  status: "APPROVED", created_at: "2026-11-12T00:00:00Z"
}}]);
out.bug60_first_approved_button_enabled = apvBtnHtml.includes('data-approve-ticket="apv_second"') && !doneBtnHtml.includes('data-approve-ticket="apv_done"');
const creditPayload = buildAdjustmentSubmitPayload("INV-202611-0012", 150, "CREDIT");
const negInputPayload = buildAdjustmentSubmitPayload("INV-202611-0012", -150, "CREDIT");
const debitPayload = buildAdjustmentSubmitPayload("INV-202611-0012", 40, "DEBIT");
out.bug60_credit_adjustment_negative_delta = (
  creditPayload.delta_cents === -15000 &&
  negInputPayload.delta_cents === -15000 &&
  debitPayload.delta_cents === 4000
);

console.log(JSON.stringify(out));
"""
    proc = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "node frontend probe failed")
    return json.loads(proc.stdout.strip().splitlines()[-1])


def evaluate_a1_and_b(delivery_dir: Path) -> Dict[str, Any]:
    """在隔离临时库上执行 A1（60 项暗病，25 分）与 B（24 项防诱导与静音回归，20 分）。"""
    weights = _load_bug_weights()
    tmp_dir = tempfile.mkdtemp(prefix="eval_yunce_v4_")
    a1_results: Dict[str, Dict[str, Any]] = {}
    b_results: List[Dict[str, Any]] = []
    severe_flags: List[str] = []

    try:
        # ==================================================================
        # 域 1：计量归集与套餐协议链路 (BUG-01 ~ BUG-09)
        # ==================================================================
        db_d1 = _copy_fresh_template_db(tmp_dir, "d1.db")
        app_d1 = _load_delivery_app(delivery_dir, db_d1)
        client_d1 = app_d1.test_client()

        # BUG-01: 变配缓存失效 + 双写/刷盘保留事件发生时点套餐
        c_b01 = []
        try:
            h12 = {"X-Tenant-Token": "tok_cust_012"}
            r0 = client_d1.get("/api/subscriptions/current?period_key=2026-11", headers=h12)
            assert r0.status_code == 200 and r0.get_json()["quota"]["plan_code"] == "PRO"
            r_chg = client_d1.post("/api/subscriptions/change-plan", headers=h12, json={"plan_code": "STARTER"})
            assert r_chg.status_code == 200
            r1 = client_d1.get("/api/subscriptions/current?period_key=2026-11", headers=h12)
            c_b01.append((
                "cache_invalidated_on_plan_change",
                r1.status_code == 200 and r1.get_json()["quota"]["plan_code"] == "STARTER" and r1.get_json()["quota"]["included_quota"] == 10000,
            ))

            from app.infra.db import tx_context  # type: ignore
            from app.jobs.metering_flush_job import flush_usage_events  # type: ignore

            h02 = {"X-Tenant-Token": "tok_cust_002"}  # PRO (50,000)
            with tx_context(db_d1, immediate=True) as conn:
                conn.execute("DELETE FROM usage_events WHERE tenant_id = 't_cust_002' AND period_key = '2026-11'")
                conn.execute("DELETE FROM usage_summaries WHERE tenant_id = 't_cust_002' AND period_key = '2026-11'")
            assert client_d1.post("/api/usage/events", headers=h02, json={"quantity": 40000, "period_key": "2026-11"}).status_code == 201
            assert client_d1.post("/api/subscriptions/change-plan", headers=h02, json={"plan_code": "STARTER"}).status_code == 200
            assert client_d1.post("/api/usage/events", headers=h02, json={"quantity": 2000, "period_key": "2026-11"}).status_code == 201
            with tx_context(db_d1, immediate=True) as conn:
                flush_usage_events(conn)
                segs = {
                    r["plan_code"]: int(r["total_quantity"])
                    for r in conn.execute(
                        "SELECT plan_code, total_quantity FROM usage_summaries WHERE tenant_id = 't_cust_002' AND period_key = '2026-11'"
                    ).fetchall()
                }
            c_b01.append(("dual_write_and_flush_preserve_event_plan", segs.get("PRO") == 40000 and segs.get("STARTER") == 2000))
        except Exception as e:
            c_b01.append(("bug01_probe", False, str(e)))
        _record_bug(a1_results, weights, "BUG-01", c_b01)

        # BUG-02: 期中变配分段独立计费 + 定制累计阶梯区间宽度不减 1
        c_b02 = []
        try:
            from app.domain.pricing import calculate_cycle_bill, compute_custom_tier_overage_cents  # type: ignore
            from app.infra.db import tx_context  # type: ignore

            with tx_context(db_d1, immediate=True) as conn:
                conn.execute("DELETE FROM usage_summaries WHERE tenant_id = 't_cust_001' AND period_key = '2026-11'")
                conn.execute(
                    "INSERT INTO usage_summaries (tenant_id, period_key, plan_code, total_quantity, updated_at) VALUES ('t_cust_001', '2026-11', 'PRO', 45000, '2026-11-10T00:00:00Z')"
                )
                conn.execute(
                    "INSERT INTO usage_summaries (tenant_id, period_key, plan_code, total_quantity, updated_at) VALUES ('t_cust_001', '2026-11', 'STARTER', 12000, '2026-11-12T00:00:00Z')"
                )
                bill_seg = calculate_cycle_bill(conn, "t_cust_001", "2026-11", "STARTER")
            c_b02.append(("segmented_midcycle_overage_accurate", bill_seg["overage_fee_cents"] == 6000 and bill_seg["total_cents"] == 25900))
            custom_ov = compute_custom_tier_overage_cents(25000, 10000, [(10000, 3), (50000, 2), (None, 1)])
            custom_edge = compute_custom_tier_overage_cents(20000, 10000, [(10000, 3), (50000, 2), (None, 1)])
            c_b02.append(("custom_cumulative_tier_no_off_by_one", custom_ov == 40000 and custom_edge == 30000))
        except Exception as e:
            c_b02.append(("bug02_probe", False, str(e)))
        _record_bug(a1_results, weights, "BUG-02", c_b02)

        # BUG-03: 动态布尔配置字符串 'false' 判假 + 升配剩余天数按比例折算不归零
        c_b03 = []
        try:
            from app.domain.pricing import calculate_upgrade_proration  # type: ignore
            from app.infra.db import tx_context  # type: ignore
            from app.infra.runtime_config_loader import get_runtime_bool_flag  # type: ignore

            future_end = (datetime.now(timezone.utc) + timedelta(days=15, hours=12)).strftime("%Y-%m-%dT%H:%M:%SZ")
            with tx_context(db_d1, immediate=True) as conn:
                flag_val = get_runtime_bool_flag(conn, "waive_upgrade_proration_promo_window", default=False)
                conn.execute("UPDATE subscriptions SET plan_code = 'STARTER', cycle_end = ? WHERE tenant_id = 't_cust_001'", (future_end,))
            c_b03.append(("runtime_config_false_string_parsed_false", flag_val is False))
            r_up = client_d1.post("/api/subscriptions/change-plan", headers={"X-Tenant-Token": "tok_cust_001"}, json={"plan_code": "PRO"})
            pror_fn = calculate_upgrade_proration("STARTER", "PRO", 15, 30)
            pror_api = int((r_up.get_json() or {}).get("proration_cents", 0)) if r_up.status_code == 200 else -1
            c_b03.append(("upgrade_proration_fractional_days_nonzero", pror_fn == 20000 and pror_api == 20000))
        except Exception as e:
            c_b03.append(("bug03_probe", False, str(e)))
        _record_bug(a1_results, weights, "BUG-03", c_b03)

        # BUG-04: 单笔与批量拒绝 quantity <= 0 + 批量东八区跨月时间戳转 UTC 归属正确账期
        c_b04 = []
        try:
            h08 = {"X-Tenant-Token": "tok_cust_008"}
            r_z1 = client_d1.post("/api/usage/events", headers=h08, json={"quantity": 0, "period_key": "2026-11"})
            r_n1 = client_d1.post("/api/usage/events", headers=h08, json={"quantity": -5, "period_key": "2026-11"})
            r_zb = client_d1.post(
                "/api/usage/batch",
                headers=h08,
                json={"events": [{"event_id": "ev_zero_b04", "quantity": 0, "occurred_at": "2026-11-10T08:00:00+08:00"}]},
            )
            c_b04.append(("reject_zero_and_negative_usage_single_and_batch", r_z1.status_code == 400 and r_n1.status_code == 400 and r_zb.status_code == 400))

            r_tz = client_d1.post(
                "/api/usage/batch",
                headers=h08,
                json={"events": [{"event_id": "ev_tz_cross_b04_unique", "quantity": 120, "occurred_at": "2026-12-01T00:30:00+08:00"}]},
            )
            from app.infra.db import get_connection  # type: ignore

            c_tmp = get_connection(db_d1)
            row_tz = c_tmp.execute("SELECT period_key FROM usage_events WHERE id = 'ev_tz_cross_b04_unique'").fetchone()
            c_tmp.close()
            c_b04.append(("batch_timezone_converted_to_utc_period", r_tz.status_code == 201 and bool(row_tz and row_tz["period_key"] == "2026-11")))
        except Exception as e:
            c_b04.append(("bug04_probe", False, str(e)))
        _record_bug(a1_results, weights, "BUG-04", c_b04)

        # BUG-05 [潜伏]: 批量上报重放数据库已存在 event_id 幂等跳过不报 500 + 滑窗环同 8 字符前缀不误杀
        c_b05 = []
        try:
            h08 = {"X-Tenant-Token": "tok_cust_008"}
            r_p1 = client_d1.post(
                "/api/usage/batch",
                headers=h08,
                json={"events": [
                    {"event_id": "gw_202611_alpha_001", "quantity": 50, "occurred_at": "2026-11-11T10:00:00Z"},
                    {"event_id": "gw_202611_beta_002", "quantity": 70, "occurred_at": "2026-11-11T10:01:00Z"},
                ]},
            )
            from app.gateway_ingest.batch_ingest_service import default_ingest_ring  # type: ignore

            default_ingest_ring.clear()
            r_replay = client_d1.post(
                "/api/usage/batch",
                headers=h08,
                json={"events": [
                    {"event_id": "gw_202611_alpha_001", "quantity": 50, "occurred_at": "2026-11-11T10:00:00Z"},
                    {"event_id": "gw_202611_gamma_003", "quantity": 30, "occurred_at": "2026-11-11T10:02:00Z"},
                ]},
            )
            j_p1 = r_p1.get_json() or {}
            j_rep = r_replay.get_json() or {}
            c_b05.append(("bloom_ring_no_8char_prefix_false_drop", r_p1.status_code == 201 and j_p1.get("accepted_count") == 2))
            c_b05.append(("db_persisted_event_replay_idempotent_no_500", r_replay.status_code == 201 and j_rep.get("accepted_count") == 1 and j_rep.get("duplicate_count") == 1))
        except Exception as e:
            c_b05.append(("bug05_probe", False, str(e)))
        _record_bug(a1_results, weights, "BUG-05", c_b05)

        # BUG-06 [潜伏]: 多区域网关分片归并器累加同账期分片且拒绝非正数分片
        c_b06 = []
        try:
            h09 = {"X-Tenant-Token": "tok_cust_009"}
            r_sh = client_d1.post(
                "/api/usage/merge-shards",
                headers=h09,
                json={
                    "shards": [
                        {"region": "cn-shanghai", "period_key": "2026-11", "quantity": 1200},
                        {"region": "cn-beijing", "period_key": "2026-11", "quantity": 850},
                        {"region": "cn-shenzhen", "period_key": "2026-11", "quantity": 450},
                    ]
                },
            )
            r_bad_sh = client_d1.post(
                "/api/usage/merge-shards",
                headers=h09,
                json={"shards": [{"region": "cn-shanghai", "period_key": "2026-11", "quantity": -100}]},
            )
            j_sh = r_sh.get_json() or {}
            c_b06.append(("regional_shards_accumulated_without_overwrite", r_sh.status_code == 201 and j_sh.get("total_merged_quantity") == 2500))
            c_b06.append(("regional_shards_reject_non_positive_quantity", r_bad_sh.status_code == 400))
        except Exception as e:
            c_b06.append(("bug06_probe", False, str(e)))
        _record_bug(a1_results, weights, "BUG-06", c_b06)

        # BUG-07: 周期算费传入账期时间锚点剔除过期框架合同 + credit_memo_bps 不得击穿最低保底线
        c_b07 = []
        try:
            from app.domain.contracts import apply_enterprise_contract_terms  # type: ignore
            from app.domain.pricing import calculate_cycle_bill  # type: ignore
            from app.infra.db import tx_context  # type: ignore

            with tx_context(db_d1, immediate=True) as conn:
                bill_exp = calculate_cycle_bill(conn, "t_cust_061", "2026-11", "ENTERPRISE")
                conn.execute(
                    """INSERT INTO enterprise_contracts
                       (id, tenant_id, min_monthly_commit_cents, custom_overage_discount_bps, credit_memo_bps, credit_limit_cents, signed_by, valid_from, valid_until, status)
                       VALUES ('ctr_probe_b07', 't_cust_030', 220000, 0, 1000, 0, 'ka_vp', '2026-01-01T00:00:00Z', '2027-01-01T00:00:00Z', 'ACTIVE')"""
                )
                terms_floor = apply_enterprise_contract_terms(conn, "t_cust_030", 199900, 10000, as_of_iso="2026-11-15T00:00:00Z")
            c_b07.append(("expired_enterprise_contract_not_applied_in_nov", bill_exp["base_fee_cents"] == 199900 and bill_exp["total_cents"] == 199900))
            c_b07.append(("credit_memo_does_not_breach_min_monthly_commit", terms_floor["subtotal_cents"] == 220000))
        except Exception as e:
            c_b07.append(("bug07_probe", False, str(e)))
        _record_bug(a1_results, weights, "BUG-07", c_b07)

        # BUG-08 [潜伏]: SLA 极端故障赔付以当期月费 100% 封顶 + 扫描任务重跑幂等不重复签发贷项单
        c_b08 = []
        try:
            from app.domain.sla_calculator import compute_sla_breach_credit  # type: ignore
            from app.infra.db import tx_context  # type: ignore
            from app.jobs.sla_credit_scan_job import run_sla_credit_scan_job  # type: ignore

            sla_extreme = compute_sla_breach_credit("ENTERPRISE", 199900, 8850)
            c_b08.append(("sla_credit_capped_at_100pct_monthly_fee", sla_extreme["credit_cents"] == 199900))
            with tx_context(db_d1, immediate=True) as conn:
                run_sla_credit_scan_job(conn, "2026-11")
                run_sla_credit_scan_job(conn, "2026-11")
                cn_rows = conn.execute(
                    "SELECT credit_cents FROM credit_notes WHERE tenant_id = 't_cust_015' AND source_invoice_id = 'SLA:2026-11'"
                ).fetchall()
            c_b08.append(("sla_scan_job_idempotent_and_capped", len(cn_rows) == 1 and int(cn_rows[0]["credit_cents"]) == 199900))
        except Exception as e:
            c_b08.append(("bug08_probe", False, str(e)))
        _record_bug(a1_results, weights, "BUG-08", c_b08)

        # BUG-09 [潜伏]: 资费策略链缓存深拷贝防跨请求污染 + 价目表覆盖默认列表不跨调用累积
        c_b09 = []
        try:
            from app.billing_ext.custom_price_book_overrides import compile_tenant_price_book_override  # type: ignore
            from app.enterprise_catalog_rules.tariff_strategy_chain import default_tariff_quote_proxy  # type: ignore

            q1 = default_tariff_quote_proxy.evaluate_node("STARTER", "CN_VAT_6_INCLUSIVE")
            q1["base_monthly_cents"] = 999999
            q1["preview_notes"].append("mutated")
            q2 = default_tariff_quote_proxy.evaluate_node("STARTER", "CN_VAT_6_INCLUSIVE")
            c_b09.append(("tariff_cache_returns_isolated_copy", q2["base_monthly_cents"] == 19900 and q2["preview_notes"] == ["CATALOG_STANDARD"]))

            p1 = compile_tenant_price_book_override("PRO", discount_bps=500)
            p2 = compile_tenant_price_book_override("PRO", discount_bps=1000)
            c_b09.append(("pricebook_override_no_mutable_default_accumulation", len(p1["audit_trail"]) == 1 and len(p2["audit_trail"]) == 1))
        except Exception as e:
            c_b09.append(("bug09_probe", False, str(e)))
        _record_bug(a1_results, weights, "BUG-09", c_b09)

        # ==================================================================
        # 域 2：钱包双账本与自动结算链路 (BUG-10 ~ BUG-18)
        # ==================================================================
        db_d2 = _copy_fresh_template_db(tmp_dir, "d2.db")
        app_d2 = _load_delivery_app(delivery_dir, db_d2)
        client_d2 = app_d2.test_client()

        # BUG-10: 混合支付退款禁止将赠送金洗成现金 + 恢复 promo_grants 剩余额度与 ACTIVE 状态
        c_b10 = []
        try:
            from app.domain.ledger import get_wallet, pay_invoice_from_wallet  # type: ignore
            from app.infra.db import tx_context  # type: ignore

            with tx_context(db_d2, immediate=True) as conn:
                w0 = get_wallet(conn, "t_cust_008")
                cash0 = int(w0["cash_balance_cents"])  # 382848, promo=10000 (pg_cust_008)
                conn.execute(
                    """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
                       base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
                       currency_unit, status, created_at, updated_at)
                       VALUES ('INV-P-B10', 't_cust_008', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z',
                       'STARTER', 15000, 0, 0, 0, 15000, 0, 0, 'CENTS', 'OPEN', '2026-11-12T00:00:00Z', '2026-11-12T00:00:00Z')"""
                )
                pay_invoice_from_wallet(conn, "INV-P-B10", "t_cust_008", idempotency_key="idem-b10")
            r_ref = client_d2.post(
                "/api/invoices/INV-P-B10/refund",
                headers={"X-Admin-Key": ADMIN_KEY},
                json={"refund_cents": 12000, "reason": "probe_b10"},
            )
            with tx_context(db_d2) as conn:
                w1 = get_wallet(conn, "t_cust_008")
                pg = conn.execute("SELECT remaining_cents, status FROM promo_grants WHERE id = 'pg_cust_008'").fetchone()
            no_wash = (
                r_ref.status_code == 200
                and int(w1["cash_balance_cents"]) <= cash0
                and int(w1["promo_balance_cents"]) >= 7000
                and (int(w1["cash_balance_cents"]) + int(w1["promo_balance_cents"])) == (cash0 + 10000 - 3000)
            )
            grant_restored = bool(pg and pg["status"] == "ACTIVE" and int(pg["remaining_cents"]) == int(w1["promo_balance_cents"]))
            c_b10.append(("mixed_refund_never_converts_promo_to_cash", no_wash))
            c_b10.append(("mixed_refund_restores_promo_grant_batch", grant_restored))
        except Exception as e:
            c_b10.append(("bug10_probe", False, str(e)))
        _record_bug(a1_results, weights, "BUG-10", c_b10)

        # BUG-11: 赠送金到期按 remaining 幂等清理不为负 + 支付扣款跳过已过期未跑批券并优先扣快到期券
        c_b11 = []
        try:
            from app.domain.ledger import expire_promo_grants, get_wallet, grant_promo_credit, pay_invoice_from_wallet  # type: ignore
            from app.infra.db import tx_context  # type: ignore

            with tx_context(db_d2, immediate=True) as conn:
                grant_promo_credit(conn, "t_cust_001", 8000, "2020-05-01T00:00:00Z", campaign_code="EXPIRED_OLD")
                grant_promo_credit(conn, "t_cust_001", 6000, "2099-06-01T00:00:00Z", campaign_code="SOONER_VALID")
                grant_promo_credit(conn, "t_cust_001", 9000, "2099-12-01T00:00:00Z", campaign_code="LATER_VALID")
                conn.execute(
                    """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
                       base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
                       currency_unit, status, created_at, updated_at)
                       VALUES ('INV-P-B11', 't_cust_001', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z',
                       'STARTER', 16000, 0, 0, 0, 16000, 0, 0, 'CENTS', 'OPEN', '2026-11-12T00:00:00Z', '2026-11-12T00:00:00Z')"""
                )
                pay_res = pay_invoice_from_wallet(conn, "INV-P-B11", "t_cust_001", idempotency_key="idem-b11")
                sooner = conn.execute("SELECT remaining_cents FROM promo_grants WHERE tenant_id='t_cust_001' AND campaign_code='SOONER_VALID'").fetchone()
                later = conn.execute("SELECT remaining_cents FROM promo_grants WHERE tenant_id='t_cust_001' AND campaign_code='LATER_VALID'").fetchone()
                # 再让 LATER_VALID 部分剩余后过期，连续跑两次 expire_promo_grants
                conn.execute("UPDATE promo_grants SET expires_at = '2026-11-10T00:00:00Z' WHERE tenant_id='t_cust_001' AND campaign_code='LATER_VALID'")
                expire_promo_grants(conn, as_of_iso="2026-11-14T00:00:00Z")
                expire_promo_grants(conn, as_of_iso="2026-11-15T00:00:00Z")
                w_after = get_wallet(conn, "t_cust_001")
            c_b11.append((
                "pay_skips_uncleaned_expired_grant_and_uses_earliest_expiry",
                pay_res["promo_paid_cents"] == 15000 and pay_res["cash_paid_cents"] == 1000 and int(sooner["remaining_cents"]) == 0,
            ))
            c_b11.append(("expire_promo_remaining_only_and_idempotent_non_negative", int(w_after["promo_balance_cents"]) == 0))
        except Exception as e:
            c_b11.append(("bug11_probe", False, str(e)))
        _record_bug(a1_results, weights, "BUG-11", c_b11)

        # BUG-12: 6 线程并发支付防双扣 + 幂等键绑定 (tenant_id, invoice_id) 防止跨单复用假成功
        c_b12 = []
        try:
            db_b12 = _copy_fresh_template_db(tmp_dir, "b12.db")
            app_b12 = _load_delivery_app(delivery_dir, db_b12)
            from app.infra.db import get_connection, tx_context  # type: ignore

            with tx_context(db_b12, immediate=True) as conn:
                w_before = int(conn.execute("SELECT cash_balance_cents FROM wallets WHERE tenant_id = 't_cust_012'").fetchone()["cash_balance_cents"])
                for iid in ("INV-CONC-12A", "INV-CONC-12B"):
                    conn.execute(
                        f"""INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
                            base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
                            currency_unit, status, created_at, updated_at)
                            VALUES ('{iid}', 't_cust_012', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z',
                            'PRO', 59900, 0, 0, 0, 59900, 0, 0, 'CENTS', 'OPEN', '2026-11-12T00:00:00Z', '2026-11-12T00:00:00Z')"""
                    )
            bar12 = threading.Barrier(6)

            def _pay12(i: int):
                bar12.wait(timeout=5)
                return app_b12.test_client().post(
                    "/api/invoices/INV-CONC-12A/pay",
                    headers={"X-Tenant-Token": "tok_cust_012", "Idempotency-Key": f"k12-{i}"},
                ).status_code

            with ThreadPoolExecutor(max_workers=6) as ex:
                sts12 = list(ex.map(_pay12, range(6)))
            win_idx = sts12.index(200) if 200 in sts12 else 0
            # 同租户另一张账单复用相同短幂等键，必须真实扣款结清而非返回上一单结果
            r_other_inv = app_b12.test_client().post(
                "/api/invoices/INV-CONC-12B/pay",
                headers={"X-Tenant-Token": "tok_cust_012", "Idempotency-Key": f"k12-{win_idx}"},
            )
            c12 = get_connection(db_b12)
            w_now = int(c12.execute("SELECT cash_balance_cents FROM wallets WHERE tenant_id = 't_cust_012'").fetchone()["cash_balance_cents"])
            cnt_a = int(c12.execute("SELECT COUNT(*) AS c FROM invoice_payments WHERE invoice_id = 'INV-CONC-12A'").fetchone()["c"])
            st_b = c12.execute("SELECT status FROM invoices WHERE id = 'INV-CONC-12B'").fetchone()["status"]
            c12.close()
            c_b12.append(("concurrent_6threads_single_debit", sts12.count(200) == 1 and cnt_a == 1))
            c_b12.append(("idempotency_key_scoped_to_invoice_and_tenant", r_other_inv.status_code == 200 and st_b == "PAID" and w_now == w_before - 119800))
        except Exception as e:
            c_b12.append(("bug12_probe", False, str(e)))
        _record_bug(a1_results, weights, "BUG-12", c_b12)

        # Reload app_d2 after app_b12 swapped sys.modules
        app_d2 = _load_delivery_app(delivery_dir, db_d2)
        client_d2 = app_d2.test_client()

        # BUG-13: 周期自动出账与手工续期同周期防重 + 停机 SUSPENDED 租户不自动滚出新周期账单
        c_b13 = []
        try:
            from app.infra.db import get_connection, tx_context  # type: ignore
            from app.jobs.settlement_job import generate_due_cycle_invoices  # type: ignore

            with tx_context(db_d2, immediate=True) as conn:
                conn.execute(
                    "UPDATE subscriptions SET cycle_start='2026-11-01T00:00:00Z', cycle_end='2026-12-01T00:00:00Z', next_billing_at='2026-11-10T00:00:00Z' WHERE tenant_id='t_cust_002'"
                )
                generate_due_cycle_invoices(conn, "2026-11-13T00:00:00Z")
                conn.execute(
                    "UPDATE subscriptions SET cycle_start='2026-11-01T00:00:00Z', cycle_end='2026-12-01T00:00:00Z', next_billing_at='2026-11-10T00:00:00Z' WHERE tenant_id='t_cust_002'"
                )
                generate_due_cycle_invoices(conn, "2026-11-13T00:00:00Z")
                conn.execute("UPDATE subscriptions SET cycle_start='2026-11-01T00:00:00Z', cycle_end='2026-12-01T00:00:00Z' WHERE tenant_id='t_cust_002'")
            client_d2.post("/api/subscriptions/renew", headers={"X-Tenant-Token": "tok_cust_002"})

            with tx_context(db_d2, immediate=True) as conn:
                conn.execute("UPDATE tenants SET status='SUSPENDED' WHERE id='t_cust_030'")
                conn.execute("UPDATE subscriptions SET status='SUSPENDED', cycle_end='2026-12-01T00:00:00Z', next_billing_at='2026-11-10T00:00:00Z' WHERE tenant_id='t_cust_030'")
                before_30 = int(conn.execute("SELECT COUNT(*) AS c FROM invoices WHERE tenant_id='t_cust_030' AND status!='VOID'").fetchone()["c"])
                generate_due_cycle_invoices(conn, "2026-11-14T00:00:00Z")
                after_30 = int(conn.execute("SELECT COUNT(*) AS c FROM invoices WHERE tenant_id='t_cust_030' AND status!='VOID'").fetchone()["c"])
                conn.execute("UPDATE tenants SET status='ACTIVE' WHERE id='t_cust_030'")
                conn.execute("UPDATE subscriptions SET status='ACTIVE' WHERE tenant_id='t_cust_030'")

            c_tmp = get_connection(db_d2)
            cnt_02 = int(c_tmp.execute(
                "SELECT COUNT(*) AS c FROM invoices WHERE tenant_id='t_cust_002' AND period_key='2026-11' AND status!='VOID'"
            ).fetchone()["c"])
            c_tmp.close()
            c_b13.append(("no_duplicate_cycle_or_manual_renew_invoice", cnt_02 == 1))
            c_b13.append(("suspended_tenant_skipped_by_cycle_invoice_job", after_30 == before_30))
        except Exception as e:
            c_b13.append(("bug13_probe", False, str(e)))
        _record_bug(a1_results, weights, "BUG-13", c_b13)

        # BUG-14: 自动结算单笔 SAVEPOINT 回退 OPEN 且写入 settlement_dlq
        c_b14 = []
        try:
            from app.infra.db import get_connection, tx_context  # type: ignore
            from app.jobs.settlement_job import settle_open_invoices  # type: ignore

            with tx_context(db_d2, immediate=True) as conn:
                conn.execute("UPDATE wallets SET cash_balance_cents = 100, promo_balance_cents = 0 WHERE tenant_id = 't_cust_030'")
                conn.execute(
                    """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
                       base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
                       currency_unit, status, created_at, updated_at)
                       VALUES ('INV-P-B14', 't_cust_030', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z',
                       'ENTERPRISE', 199900, 0, 0, 0, 199900, 0, 0, 'CENTS', 'OPEN', '2026-11-12T00:00:00Z', '2026-11-12T00:00:00Z')"""
                )
                settle_open_invoices(conn)
            c_tmp = get_connection(db_d2)
            st14 = c_tmp.execute("SELECT status FROM invoices WHERE id='INV-P-B14'").fetchone()["status"]
            dlq14 = int(c_tmp.execute("SELECT COUNT(*) AS c FROM settlement_dlq WHERE invoice_id='INV-P-B14'").fetchone()["c"])
            c_tmp.close()
            c_b14.append(("failed_auto_settle_reverted_to_open", st14 == "OPEN"))
            c_b14.append(("failed_auto_settle_enqueued_to_dlq", dlq14 >= 1))
        except Exception as e:
            c_b14.append(("bug14_probe", False, str(e)))
        _record_bug(a1_results, weights, "BUG-14", c_b14)

        # BUG-15: 自动结算跳过争议冻结单 + 后台 REJECT_DISPUTE 清空冻结标记恢复自动结算
        c_b15 = []
        try:
            from app.infra.db import get_connection, tx_context  # type: ignore
            from app.jobs.settlement_job import settle_open_invoices  # type: ignore

            with tx_context(db_d2, immediate=True) as conn:
                conn.execute("UPDATE wallets SET cash_balance_cents = 200000 WHERE tenant_id = 't_cust_009'")
                conn.execute(
                    """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
                       base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
                       currency_unit, status, dispute_reason, created_at, updated_at)
                       VALUES ('INV-P-B15', 't_cust_009', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z',
                       'PRO', 59900, 0, 0, 0, 59900, 0, 0, 'CENTS', 'OPEN', '核对网关重传', '2026-11-12T00:00:00Z', '2026-11-12T00:00:00Z')"""
                )
                conn.execute(
                    "INSERT INTO dispute_tickets (id, invoice_id, tenant_id, reason, freeze_auto_debit, status, created_at) VALUES ('dsp_b15', 'INV-P-B15', 't_cust_009', '核对网关重传', 1, 'OPEN', '2026-11-12T00:00:00Z')"
                )
                settle_open_invoices(conn)
            c_tmp = get_connection(db_d2)
            st_frozen = c_tmp.execute("SELECT status FROM invoices WHERE id='INV-P-B15'").fetchone()["status"]
            c_tmp.close()
            c_b15.append(("disputed_invoice_skipped_by_auto_settle", st_frozen == "OPEN"))

            r_res = client_d2.post(
                "/api/admin/disputes/dsp_b15/resolve",
                headers={"X-Admin-Key": ADMIN_KEY},
                json={"decision": "REJECT_DISPUTE"},
            )
            with tx_context(db_d2, immediate=True) as conn:
                settle_open_invoices(conn)
            c_tmp = get_connection(db_d2)
            inv_after = c_tmp.execute("SELECT status, dispute_reason FROM invoices WHERE id='INV-P-B15'").fetchone()
            dsp_after = c_tmp.execute("SELECT freeze_auto_debit FROM dispute_tickets WHERE id='dsp_b15'").fetchone()
            c_tmp.close()
            c_b15.append((
                "rejected_dispute_unfreezes_and_settles",
                r_res.status_code == 200 and inv_after["status"] == "PAID" and not inv_after["dispute_reason"] and int(dsp_after["freeze_auto_debit"]) == 0,
            ))
        except Exception as e:
            c_b15.append(("bug15_probe", False, str(e)))
        _record_bug(a1_results, weights, "BUG-15", c_b15)

        # BUG-16: DLQ 重试仅扣剩余未付差额 + 结清后将死信状态置为 RESOLVED 防二次重扣
        c_b16 = []
        try:
            from app.infra.db import get_connection, tx_context  # type: ignore
            from app.jobs.dlq_retry_job import retry_pending_dlq  # type: ignore

            with tx_context(db_d2, immediate=True) as conn:
                conn.execute("DELETE FROM settlement_dlq")
                conn.execute("UPDATE wallets SET cash_balance_cents = 50000, promo_balance_cents = 0 WHERE tenant_id = 't_cust_004'")
                conn.execute(
                    """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
                       base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
                       currency_unit, status, created_at, updated_at)
                       VALUES ('INV-P-B16', 't_cust_004', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z',
                       'PRO', 59900, 0, 0, 0, 59900, 20000, 0, 'CENTS', 'OPEN', '2026-11-12T00:00:00Z', '2026-11-12T00:00:00Z')"""
                )
                conn.execute(
                    "INSERT INTO settlement_dlq (invoice_id, tenant_id, error_msg, retry_count, status, created_at, updated_at) VALUES ('INV-P-B16', 't_cust_004', '余额不足', 1, 'PENDING', '2026-11-12T00:00:00Z', '2026-11-12T00:00:00Z')"
                )
                retry_pending_dlq(conn)
                retry_pending_dlq(conn)
            c_tmp = get_connection(db_d2)
            w16 = int(c_tmp.execute("SELECT cash_balance_cents FROM wallets WHERE tenant_id='t_cust_004'").fetchone()["cash_balance_cents"])
            inv16 = c_tmp.execute("SELECT paid_cents, status FROM invoices WHERE id='INV-P-B16'").fetchone()
            dlq16 = c_tmp.execute("SELECT status FROM settlement_dlq WHERE invoice_id='INV-P-B16'").fetchone()
            c_tmp.close()
            c_b16.append(("dlq_charges_only_unpaid_delta_cents", w16 == 10100 and int(inv16["paid_cents"]) == 59900 and inv16["status"] == "PAID"))
            c_b16.append(("dlq_marks_entry_resolved_after_recovery", bool(dlq16 and dlq16["status"] == "RESOLVED")))
        except Exception as e:
            c_b16.append(("bug16_probe", False, str(e)))
        _record_bug(a1_results, weights, "BUG-16", c_b16)

        # BUG-17: 结算预览 GET 零写副作用不锁券 + 部分付款账单按剩余待付净额试算
        c_b17 = []
        try:
            from app.domain.ledger import grant_promo_credit  # type: ignore
            from app.infra.db import get_connection, tx_context  # type: ignore

            with tx_context(db_d2, immediate=True) as conn:
                grant_promo_credit(conn, "t_cust_012", 12000, "2099-12-31T23:59:59Z", campaign_code="PREVIEW_TEST")
                conn.execute(
                    """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
                       base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
                       currency_unit, status, created_at, updated_at)
                       VALUES ('INV-P-B17', 't_cust_012', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z',
                       'PRO', 59900, 0, 0, 0, 59900, 20000, 0, 'CENTS', 'OPEN', '2026-11-12T00:00:00Z', '2026-11-12T00:00:00Z')"""
                )
            r_pv = client_d2.get("/api/invoices/INV-P-B17/settlement-preview", headers={"X-Tenant-Token": "tok_cust_012"})
            pv = (r_pv.get_json() or {}).get("preview", {})
            c_tmp = get_connection(db_d2)
            locked_cnt = int(c_tmp.execute("SELECT COUNT(*) AS c FROM promo_grants WHERE tenant_id='t_cust_012' AND status='LOCKED_PREVIEW'").fetchone()["c"])
            c_tmp.close()
            c_b17.append(("preview_get_has_zero_db_lock_side_effect", r_pv.status_code == 200 and locked_cnt == 0))
            c_b17.append(("preview_subtracts_already_paid_cents", pv.get("due_cents") == 39900 and pv.get("estimated_promo_deduct_cents") == 12000 and pv.get("estimated_cash_deduct_cents") == 27900))
        except Exception as e:
            c_b17.append(("bug17_probe", False, str(e)))
        _record_bug(a1_results, weights, "BUG-17", c_b17)

        # BUG-18 [潜伏]: 对公水单全角括号归一化自动认领 + 人工二次认领拒绝已入账水单防双加钱
        c_b18 = []
        try:
            from app.infra.db import tx_context  # type: ignore

            with tx_context(db_d2, immediate=True) as conn:
                conn.execute("UPDATE tenants SET company_name = '云策智联科技(上海)有限公司' WHERE id = 't_cust_002'")
                w_b18_0 = int(conn.execute("SELECT cash_balance_cents FROM wallets WHERE tenant_id = 't_cust_002'").fetchone()["cash_balance_cents"])
            csv_line = "serial_no,payer_name,amount_cents,tx_date\nCMB20261114B18,云策智联科技（上海）有限公司,59900,2026-11-14"
            r_imp = client_d2.post("/api/admin/bank-statements/import", headers={"X-Admin-Key": ADMIN_KEY}, json={"csv_text": csv_line})
            imp_json = r_imp.get_json() or {}
            c_b18.append(("fullwidth_parens_normalized_for_auto_claim", r_imp.status_code == 200 and imp_json.get("auto_claimed_count") == 1))

            with tx_context(db_d2) as conn:
                bsi_row = conn.execute("SELECT id FROM bank_statement_imports WHERE bank_serial_no = 'CMB20261114B18'").fetchone()
            bsi_id = bsi_row["id"] if bsi_row else "bsi_0001"
            r_dup_claim = client_d2.post(
                f"/api/admin/bank-statements/{bsi_id}/claim",
                headers={"X-Admin-Key": ADMIN_KEY},
                json={"tenant_id": "t_cust_002"},
            )
            with tx_context(db_d2) as conn:
                w_b18_1 = int(conn.execute("SELECT cash_balance_cents FROM wallets WHERE tenant_id = 't_cust_002'").fetchone()["cash_balance_cents"])
            c_b18.append(("manual_claim_blocks_already_claimed_statement", r_dup_claim.status_code == 400 and w_b18_1 == w_b18_0 + 59900))
        except Exception as e:
            c_b18.append(("bug18_probe", False, str(e)))
        _record_bug(a1_results, weights, "BUG-18", c_b18)

        # ==================================================================
        # 域 3：多币种锁汇与跨境财资链路 (BUG-19 ~ BUG-24)
        # ==================================================================
        db_d3 = _copy_fresh_template_db(tmp_dir, "d3.db")
        app_d3 = _load_delivery_app(delivery_dir, db_d3)
        client_d3 = app_d3.test_client()

        # BUG-19: 外币锁汇取账单出账日<=最近有效牌价（不落 7.0 兜底）且保留万分比小数精度四舍五入
        c_b19 = []
        try:
            from app.infra.db import tx_context  # type: ignore

            with tx_context(db_d3, immediate=True) as conn:
                conn.execute(
                    """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
                       base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
                       currency_unit, status, created_at, updated_at)
                       VALUES ('INV-P-B19', 't_cust_029', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z',
                       'PRO', 10000, 0, 0, 0, 10000, 0, 0, 'CENTS', 'OPEN', '2026-11-03T09:00:00Z', '2026-11-03T09:00:00Z')"""
                )
            # 2026-11-03 出账应命中 2026-11-01 USD 牌价 71850 (7.1850)，而非 11-12 的 72400 或兜底 70000；$123.45 -> round(12345 * 7.1850) = 88699 分
            r_fx = client_d3.post(
                "/api/invoices/INV-P-B19/fx-settle",
                headers={"X-Tenant-Token": "tok_cust_029"},
                json={"currency": "USD", "foreign_amount_minor": 12345},
            )
            fx_j = r_fx.get_json() or {}
            c_b19.append(("fx_uses_invoice_issue_date_effective_rate", r_fx.status_code == 200 and fx_j.get("applied_rate_bps") == 71850))
            c_b19.append(("fx_bps_retains_decimal_precision", fx_j.get("settled_cny_cents") == 88699))
        except Exception as e:
            c_b19.append(("bug19_probe", False, str(e)))
        _record_bug(a1_results, weights, "BUG-19", c_b19)

        # BUG-20 [潜伏]: 月末外币重估剔除已 PAID / VOID 账单且汇兑损益正负方向符合应收准则
        c_b20 = []
        try:
            from app.infra.db import tx_context  # type: ignore

            with tx_context(db_d3, immediate=True) as conn:
                conn.execute("DELETE FROM fx_settlement_logs")
                conn.execute(
                    """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
                       base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
                       currency_unit, status, created_at, updated_at)
                       VALUES ('INV-FX-OPEN', 't_cust_029', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z',
                       'PRO', 71850, 0, 0, 0, 71850, 0, 0, 'CENTS', 'OPEN', '2026-11-02T00:00:00Z', '2026-11-02T00:00:00Z')"""
                )
                conn.execute(
                    """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
                       base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
                       currency_unit, status, created_at, updated_at)
                       VALUES ('INV-FX-PAID', 't_cust_029', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z',
                       'PRO', 71850, 0, 0, 0, 71850, 71850, 0, 'CENTS', 'PAID', '2026-11-02T00:00:00Z', '2026-11-02T00:00:00Z')"""
                )
                conn.execute(
                    "INSERT INTO fx_settlement_logs (id, invoice_id, tenant_id, currency_code, foreign_minor_units, applied_rate_bps, settled_cny_cents, created_at) VALUES ('fxl_open', 'INV-FX-OPEN', 't_cust_029', 'USD', 10000, 71850, 71850, '2026-11-02T00:00:00Z')"
                )
                conn.execute(
                    "INSERT INTO fx_settlement_logs (id, invoice_id, tenant_id, currency_code, foreign_minor_units, applied_rate_bps, settled_cny_cents, created_at) VALUES ('fxl_paid', 'INV-FX-PAID', 't_cust_029', 'USD', 10000, 71850, 71850, '2026-11-02T00:00:00Z')"
                )
            # 期末汇率升至 72850 -> 10000 USD minor 应收人民币从 71850 升至 72850，产生 +1000 分未实现汇兑收益；期末降至 70850 -> -1000 分损失
            r_up_fx = client_d3.post("/api/admin/treasury/fx-reval/2026-11", headers={"X-Admin-Key": ADMIN_KEY}, json={"closing_rates_bps": {"USD": 72850}})
            r_dn_fx = client_d3.post("/api/admin/treasury/fx-reval/2026-11", headers={"X-Admin-Key": ADMIN_KEY}, json={"closing_rates_bps": {"USD": 70850}})
            j_up = r_up_fx.get_json() or {}
            j_dn = r_dn_fx.get_json() or {}
            c_b20.append(("fx_reval_excludes_settled_and_void_invoices", j_up.get("revalued_count") == 1))
            c_b20.append(("fx_reval_gain_loss_sign_matches_cas19", j_up.get("net_unrealized_fx_gain_loss_cents") == 1000 and j_dn.get("net_unrealized_fx_gain_loss_cents") == -1000))
        except Exception as e:
            c_b20.append(("bug20_probe", False, str(e)))
        _record_bug(a1_results, weights, "BUG-20", c_b20)

        # BUG-21: 常规跨境 SaaS 订阅免征预提税 (0%) + 特许权包税 Gross-up 按 (1 - wht) 倒算
        c_b21 = []
        try:
            r_saas = client_d3.post(
                "/api/admin/treasury/wht-calc",
                headers={"X-Admin-Key": ADMIN_KEY},
                json={"invoice_net_cents": 100000, "jurisdiction_code": "SG", "has_tax_residency_cert": True, "contract_gross_up_clause": False, "is_royalty_license": False},
            )
            r_roy_gu = client_d3.post(
                "/api/admin/treasury/wht-calc",
                headers={"X-Admin-Key": ADMIN_KEY},
                json={"invoice_net_cents": 90000, "jurisdiction_code": "JP", "has_tax_residency_cert": True, "contract_gross_up_clause": True, "is_royalty_license": True},
            )
            js_saas = r_saas.get_json() or {}
            js_gu = r_roy_gu.get_json() or {}
            c_b21.append(("standard_saas_exempt_from_royalty_wht", js_saas.get("wht_withheld_cents") == 0 and js_saas.get("net_cash_remitted_cents") == 100000))
            c_b21.append(("royalty_gross_up_uses_1_minus_rate_denominator", js_gu.get("billed_gross_cents") == 100000 and js_gu.get("wht_withheld_cents") == 10000))
        except Exception as e:
            c_b21.append(("bug21_probe", False, str(e)))
        _record_bug(a1_results, weights, "BUG-21", c_b21)

        # BUG-22 [潜伏]: 纯赠送金 0 现金交易不计提支付通道保底手续费
        c_b22 = []
        try:
            from app.treasury.payment_channel_router import CHANNELS, estimate_channel_acquiring_fee_cents  # type: ignore

            fee0 = estimate_channel_acquiring_fee_cents(CHANNELS["WECHAT_NATIVE_V2"], 0)
            r_ch = client_d3.get("/api/admin/treasury/channel-fees/2026-11", headers={"X-Admin-Key": ADMIN_KEY})
            ch_j = r_ch.get_json() or {}
            c_b22.append(("zero_cash_payment_incurs_zero_channel_fee", fee0 == 0 and ch_j.get("zero_cash_charged_count") == 0))
        except Exception as e:
            c_b22.append(("bug22_probe", False, str(e)))
        _record_bug(a1_results, weights, "BUG-22", c_b22)

        # BUG-23: 履约保证金抵缴同步更新账单 paid_cents / status 并写入 invoice_payments
        c_b23 = []
        try:
            from app.infra.db import get_connection, tx_context  # type: ignore

            with tx_context(db_d3, immediate=True) as conn:
                conn.execute("INSERT OR REPLACE INTO escrow_accounts (tenant_id, initial_deposit_cents, balance_cents, frozen_cents, status, updated_at) VALUES ('t_cust_004', 300000, 300000, 0, 'ACTIVE', '2026-11-12T00:00:00Z')")
            r_esc = client_d3.post(
                "/api/admin/escrow/apply-to-invoice",
                headers={"X-Admin-Key": ADMIN_KEY},
                json={"tenant_id": "t_cust_004", "invoice_id": "INV-202611-0004", "amount_cents": 220000},
            )
            c_tmp = get_connection(db_d3)
            inv_esc = c_tmp.execute("SELECT paid_cents, status FROM invoices WHERE id='INV-202611-0004'").fetchone()
            pay_esc = int(c_tmp.execute("SELECT COALESCE(SUM(total_paid_cents), 0) AS s FROM invoice_payments WHERE invoice_id='INV-202611-0004'").fetchone()["s"])
            esc_bal = int(c_tmp.execute("SELECT balance_cents FROM escrow_accounts WHERE tenant_id='t_cust_004'").fetchone()["balance_cents"])
            c_tmp.close()
            c_b23.append(("escrow_offset_updates_invoice_paid_and_status", r_esc.status_code == 200 and int(inv_esc["paid_cents"]) == 220000 and inv_esc["status"] == "PAID"))
            c_b23.append(("escrow_offset_records_payment_and_deducts_balance", pay_esc == 220000 and esc_bal == 80000))
        except Exception as e:
            c_b23.append(("bug23_probe", False, str(e)))
        _record_bug(a1_results, weights, "BUG-23", c_b23)

        # BUG-24 [潜伏]: 集团外部净营收剔除内部关联交易结算主体 (intercompany / internal_settlement)
        c_b24 = []
        try:
            from app.infra.db import tx_context  # type: ignore

            r_ic0 = client_d3.get("/api/admin/diagnostics/intercompany/2026-10", headers={"X-Admin-Key": ADMIN_KEY})
            base_ext_oct = int((r_ic0.get_json() or {}).get("external_revenue_summary", {}).get("consolidated_external_gross_cents", -1))
            with tx_context(db_d3, immediate=True) as conn:
                conn.execute(
                    """INSERT INTO tenants (id, company_name, status, schema_version, api_token, tax_profile_code, billing_metadata, created_at)
                       VALUES ('t_ic_probe', '深圳云策内部研发结算主体', 'ACTIVE', 2, 'tok_ic_probe', 'CN_VAT_6_INCLUSIVE', '{"intercompany": true, "entity_code": "CN_SZ_RD"}', '2026-01-01T00:00:00Z')"""
                )
                conn.execute(
                    """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
                       base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
                       currency_unit, status, created_at, updated_at)
                       VALUES ('INV-IC-OCT', 't_ic_probe', '2026-10', '2026-10-01T00:00:00Z', '2026-11-01T00:00:00Z',
                       'ENTERPRISE', 500000, 0, 0, 0, 500000, 500000, 0, 'CENTS', 'PAID', '2026-10-15T00:00:00Z', '2026-10-15T00:00:00Z')"""
                )
            r_ic1 = client_d3.get("/api/admin/diagnostics/intercompany/2026-10", headers={"X-Admin-Key": ADMIN_KEY})
            after_ext_oct = int((r_ic1.get_json() or {}).get("external_revenue_summary", {}).get("consolidated_external_gross_cents", -2))
            # 同时核验模板库 2026-11 已内建的内部关联主体账单已被剔除
            r_ic_nov = client_d3.get("/api/admin/diagnostics/intercompany/2026-11", headers={"X-Admin-Key": ADMIN_KEY})
            with tx_context(db_d3) as conn:
                all_nov_sum = int(conn.execute("SELECT SUM(CASE WHEN currency_unit='YUAN_STR' THEN CAST(ROUND(CAST(REPLACE(REPLACE(raw_legacy_total,'¥',''),',','') AS REAL)*100) AS INTEGER) ELSE total_cents END) FROM invoices WHERE period_key='2026-11' AND status!='VOID'").fetchone()[0])
            nov_ext = int((r_ic_nov.get_json() or {}).get("external_revenue_summary", {}).get("consolidated_external_gross_cents", -1))
            c_b24.append(("intercompany_metadata_tenant_excluded_from_external_revenue", base_ext_oct == after_ext_oct and nov_ext < all_nov_sum))
        except Exception as e:
            c_b24.append(("bug24_probe", False, str(e)))
        _record_bug(a1_results, weights, "BUG-24", c_b24)

        # ==================================================================
        # 域 4：金税数电票与跨期调账链路 (BUG-25 ~ BUG-31)
        # ==================================================================
        db_d4 = _copy_fresh_template_db(tmp_dir, "d4.db")
        app_d4 = _load_delivery_app(delivery_dir, db_d4)
        client_d4 = app_d4.test_client()

        # BUG-25: 移除启动期双紧急热补丁（>=2000元价外增值税不抹零 + 数电票单张上限恢复 10 万元不碎拆）
        c_b25 = []
        try:
            from app.domain.pricing import calculate_cycle_bill  # type: ignore
            from app.infra.db import tx_context  # type: ignore

            with tx_context(db_d4) as conn:
                bill_hv = calculate_cycle_bill(conn, "t_cust_051", "2026-11", "ENTERPRISE")
            c_b25.append(("high_value_exclusive_vat_not_zeroed_by_hotfix", bill_hv["tax_cents"] == 13194 and bill_hv["total_cents"] == 233094))

            r_fp15 = client_d4.post(
                "/api/fapiao/apply",
                headers={"X-Tenant-Token": "tok_cust_015"},
                json={"invoice_id": "INV-202611-0015", "buyer_tax_id": "91310115MA1B25015X"},
            )
            fp15_j = r_fp15.get_json() or {}
            c_b25.append(("fapiao_single_sheet_ceiling_not_500yuan_hotfix", r_fp15.status_code in (200, 201) and fp15_j.get("sheet_count") == 1))
        except Exception as e:
            c_b25.append(("bug25_probe", False, str(e)))
        _record_bug(a1_results, weights, "BUG-25", c_b25)

        # BUG-26: 金税四期销项底账循环翻页突破 50 条截断 + 剔除已红冲原蓝票 RED_REVERSED 与 VOID
        c_b26 = []
        try:
            from app.infra.db import tx_context  # type: ignore

            with tx_context(db_d4, immediate=True) as conn:
                conn.execute(
                    """INSERT INTO fapiao_requests (id, tenant_id, invoice_id, fapiao_type, buyer_tax_id, title,
                       net_amount_cents, tax_amount_cents, gross_amount_cents, sheet_count, status, red_letter_of, created_at)
                       VALUES ('FP-VOID-B26', 't_cust_001', 'INV-202610-0001', 'VAT_SPECIAL_E', '91310115MA1VOID26X', '作废蓝票测试',
                       18774, 1126, 19900, 1, 'VOID', NULL, '2026-10-20T00:00:00Z')"""
                )
            r_g4 = client_d4.get("/api/fapiao/reconcile/2026-10", headers={"X-Admin-Key": ADMIN_KEY})
            g4_j = r_g4.get_json() or {}
            c_b26.append((
                "golden4_sdk_paginates_all_pages_and_excludes_reversed_or_void",
                r_g4.status_code == 200 and g4_j.get("gross_total_cents") == 5921093 and g4_j.get("tax_total_cents") == 335162,
            ))
        except Exception as e:
            c_b26.append(("bug26_probe", False, str(e)))
        _record_bug(a1_results, weights, "BUG-26", c_b26)

        # BUG-27: 数电开票与拆票预览消除双重向下取整 1 分钱尾差，且预览按实付现金净额（扣除赠金与现金退费）计算
        c_b27 = []
        try:
            from app.infra.db import tx_context  # type: ignore

            with tx_context(db_d4, immediate=True) as conn:
                conn.execute(
                    """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
                       base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
                       currency_unit, status, created_at, updated_at)
                       VALUES ('INV-P-B27', 't_cust_008', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z',
                       'STARTER', 19900, 0, 0, 0, 19900, 19900, 0, 'CENTS', 'PAID', '2026-11-12T00:00:00Z', '2026-11-12T00:00:00Z')"""
                )
                conn.execute(
                    """INSERT INTO invoice_payments (id, invoice_id, tenant_id, idempotency_key, cash_paid_cents, promo_paid_cents, total_paid_cents, created_at)
                       VALUES ('pay_p_b27', 'INV-P-B27', 't_cust_008', 'idem_b27', 15900, 4000, 19900, '2026-11-12T00:05:00Z')"""
                )
            r_sp = client_d4.get("/api/fapiao/split-preview/INV-P-B27", headers={"X-Tenant-Token": "tok_cust_008"})
            sp_j = r_sp.get_json() or {}
            r_ap = client_d4.post(
                "/api/fapiao/apply",
                headers={"X-Tenant-Token": "tok_cust_008"},
                json={"invoice_id": "INV-P-B27", "buyer_tax_id": "91310115MA1B27008X"},
            )
            ap_j = r_ap.get_json() or {}
            c_b27.append((
                "fapiao_apply_penny_conserved_on_non_106_multiple",
                r_ap.status_code in (200, 201)
                and int(ap_j.get("gross_amount_cents", -1)) == 15900
                and int(ap_j.get("net_amount_cents", 0)) + int(ap_j.get("tax_amount_cents", 0)) == 15900,
            ))
            c_b27.append((
                "fapiao_split_preview_uses_net_cash_and_conserves_pennies",
                r_sp.status_code == 200 and sp_j.get("total_gross_cents") == 15900 and sp_j.get("penny_conserved") is True,
            ))
        except Exception as e:
            c_b27.append(("bug27_probe", False, str(e)))
        _record_bug(a1_results, weights, "BUG-27", c_b27)

        # BUG-28: 并发开票防重开双蓝票 + 混合支付发生赠送金退款后仅扣现金退款额计算可开票净额
        c_b28 = []
        try:
            db_b28 = _copy_fresh_template_db(tmp_dir, "b28.db")
            app_b28 = _load_delivery_app(delivery_dir, db_b28)
            from app.infra.db import get_connection, tx_context  # type: ignore

            with tx_context(db_b28, immediate=True) as conn:
                conn.execute(
                    """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
                       base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
                       currency_unit, status, created_at, updated_at)
                       VALUES ('INV-CONC-28', 't_cust_008', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z',
                       'STARTER', 19900, 0, 0, 0, 19900, 19900, 4000, 'CENTS', 'PAID', '2026-11-12T00:00:00Z', '2026-11-12T00:00:00Z')"""
                )
                conn.execute(
                    """INSERT INTO invoice_payments (id, invoice_id, tenant_id, idempotency_key, cash_paid_cents, promo_paid_cents, total_paid_cents, created_at)
                       VALUES ('pay_conc_28', 'INV-CONC-28', 't_cust_008', 'idem_c28', 15900, 4000, 19900, '2026-11-12T00:05:00Z')"""
                )
                # 退回的 4000 分全部是赠送金（现金退回 0），因此客户实际现金净支出仍为 15900 分！
                conn.execute(
                    """INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at)
                       VALUES ('t_cust_008', 'REFUND', 0, 4000, 'INV-CONC-28', '退回赠金部分', '2026-11-12T01:00:00Z')"""
                )
            bar28 = threading.Barrier(4)

            def _apply28(_i: int):
                bar28.wait(timeout=5)
                return app_b28.test_client().post(
                    "/api/fapiao/apply",
                    headers={"X-Tenant-Token": "tok_cust_008"},
                    json={"invoice_id": "INV-CONC-28", "buyer_tax_id": "91310115MA1CONC28X"},
                )

            with ThreadPoolExecutor(max_workers=4) as ex:
                rs28 = list(ex.map(_apply28, range(4)))
            c28 = get_connection(db_b28)
            rows28 = c28.execute("SELECT * FROM fapiao_requests WHERE invoice_id='INV-CONC-28' AND status='ISSUED'").fetchall()
            c28.close()
            c_b28.append(("concurrent_fapiao_apply_issues_single_blue_record", len(rows28) == 1 and any(r.status_code in (200, 201) for r in rs28)))
            c_b28.append(("fapiao_invoiceable_cash_deducts_only_cash_refunds", len(rows28) == 1 and int(rows28[0]["gross_amount_cents"]) == 15900))
        except Exception as e:
            c_b28.append(("bug28_probe", False, str(e)))
        _record_bug(a1_results, weights, "BUG-28", c_b28)

        # Reload app_d4
        app_d4 = _load_delivery_app(delivery_dir, db_d4)
        client_d4 = app_d4.test_client()

        # BUG-29 [潜伏]: 批量红字确认单同步存负数金额、将原蓝票置为 RED_REVERSED 且拒绝重复冲红
        c_b29 = []
        try:
            from app.infra.db import get_connection, tx_context  # type: ignore

            with tx_context(db_d4, immediate=True) as conn:
                blue_row = conn.execute("SELECT id, gross_amount_cents FROM fapiao_requests WHERE status = 'ISSUED' LIMIT 1").fetchone()
            orig_fp_id = blue_row["id"]
            orig_gross = abs(int(blue_row["gross_amount_cents"]))
            r_s1 = client_d4.post(
                "/api/fapiao/sync-red-letters",
                headers={"X-Admin-Key": ADMIN_KEY},
                json={"confirmations": [{"original_fapiao_id": orig_fp_id, "red_fapiao_id": "FP-RED-PROBE29"}]},
            )
            r_s2 = client_d4.post(
                "/api/fapiao/sync-red-letters",
                headers={"X-Admin-Key": ADMIN_KEY},
                json={"confirmations": [{"original_fapiao_id": orig_fp_id, "red_fapiao_id": "FP-RED-PROBE29-DUP"}]},
            )
            c_tmp = get_connection(db_d4)
            red_r = c_tmp.execute("SELECT net_amount_cents, tax_amount_cents, gross_amount_cents FROM fapiao_requests WHERE id='FP-RED-PROBE29'").fetchone()
            orig_r = c_tmp.execute("SELECT status FROM fapiao_requests WHERE id=?", (orig_fp_id,)).fetchone()
            dup_r = c_tmp.execute("SELECT id FROM fapiao_requests WHERE id='FP-RED-PROBE29-DUP'").fetchone()
            c_tmp.close()
            c_b29.append((
                "synced_red_fapiao_has_negative_amounts_and_marks_blue_reversed",
                r_s1.status_code == 200 and bool(red_r and int(red_r["gross_amount_cents"]) == -orig_gross and int(red_r["net_amount_cents"]) < 0 and orig_r["status"] == "RED_REVERSED"),
            ))
            c_b29.append(("already_reversed_blue_fapiao_not_double_synced", r_s2.status_code in (200, 400) and dup_r is None))
        except Exception as e:
            c_b29.append(("bug29_probe", False, str(e)))
        _record_bug(a1_results, weights, "BUG-29", c_b29)

        # BUG-30: CLOSED 封账账单重算绝不改原单而在 OPEN 期写 billing_adjustments + 迟到话单路由至当前 OPEN 账期
        c_b30 = []
        try:
            from app.infra.db import get_connection, tx_context  # type: ignore
            from app.jobs.metering_flush_job import flush_usage_events  # type: ignore

            r_rec = client_d4.post("/api/invoices/INV-202609-0012/recalculate", headers={"X-Admin-Key": ADMIN_KEY})
            with tx_context(db_d4, immediate=True) as conn:
                oct_before = int(conn.execute("SELECT COALESCE(SUM(total_quantity),0) FROM usage_summaries WHERE tenant_id='t_cust_001' AND period_key='2026-10'").fetchone()[0])
                nov_before = int(conn.execute("SELECT COALESCE(SUM(total_quantity),0) FROM usage_summaries WHERE tenant_id='t_cust_001' AND period_key='2026-11'").fetchone()[0])
                conn.execute(
                    """INSERT INTO usage_events (id, tenant_id, metric_code, quantity, period_key, plan_code_at_event, occurred_at, flushed)
                       VALUES ('ev_late_oct_b30', 't_cust_001', 'api_calls', 3333, '2026-10', 'STARTER', '2026-11-12T00:00:00Z', 0)"""
                )
                flush_usage_events(conn)
            c_tmp = get_connection(db_d4)
            inv0912 = c_tmp.execute("SELECT total_cents, status FROM invoices WHERE id='INV-202609-0012'").fetchone()
            adj0912 = c_tmp.execute(
                "SELECT delta_cents, applied_period_key FROM billing_adjustments WHERE ref_invoice_id='INV-202609-0012' AND applied_period_key='2026-11'"
            ).fetchone()
            oct_after = int(c_tmp.execute("SELECT COALESCE(SUM(total_quantity),0) FROM usage_summaries WHERE tenant_id='t_cust_001' AND period_key='2026-10'").fetchone()[0])
            nov_after = int(c_tmp.execute("SELECT COALESCE(SUM(total_quantity),0) FROM usage_summaries WHERE tenant_id='t_cust_001' AND period_key='2026-11'").fetchone()[0])
            c_tmp.close()
            c_b30.append((
                "closed_invoice_recalc_preserves_history_and_books_open_adjustment",
                r_rec.status_code == 200 and int(inv0912["total_cents"]) == 119900 and bool(adj0912 and int(adj0912["delta_cents"]) == -20000),
            ))
            c_b30.append(("late_usage_for_closed_period_routed_to_open_period", oct_after == oct_before and nov_after == nov_before + 3333))
        except Exception as e:
            c_b30.append(("bug30_probe", False, str(e)))
        _record_bug(a1_results, weights, "BUG-30", c_b30)

        # BUG-31: 开放期核销调账单遵循有向符号（负减正加）且校验 PENDING 状态防同一调账单重复叠加核销
        c_b31 = []
        try:
            from app.infra.db import get_connection, tx_context  # type: ignore

            with tx_context(db_d4, immediate=True) as conn:
                conn.execute(
                    """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
                       base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
                       currency_unit, status, created_at, updated_at)
                       VALUES ('INV-P-B31', 't_cust_012', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z',
                       'PRO', 59900, 0, 0, 0, 59900, 0, 0, 'CENTS', 'OPEN', '2026-11-12T00:00:00Z', '2026-11-12T00:00:00Z')"""
                )
                conn.execute(
                    """INSERT INTO billing_adjustments (id, tenant_id, ref_invoice_id, target_period_key, applied_period_key,
                       adjustment_type, delta_cents, reason, status, created_at)
                       VALUES ('adj_b31_neg', 't_cust_012', 'INV-202610-0012', '2026-10', '2026-11',
                       'CREDIT_MEMO', -15000, '贷项减免', 'PENDING', '2026-11-13T00:00:00Z')"""
                )
                conn.execute(
                    """INSERT INTO billing_adjustments (id, tenant_id, ref_invoice_id, target_period_key, applied_period_key,
                       adjustment_type, delta_cents, reason, status, created_at)
                       VALUES ('adj_b31_pos', 't_cust_012', 'INV-202610-0012', '2026-10', '2026-11',
                       'DEBIT_MEMO', 4000, '借项补收', 'PENDING', '2026-11-13T00:00:00Z')"""
                )
            r_a1 = client_d4.post("/api/admin/adjustments/adj_b31_neg/apply", headers={"X-Admin-Key": ADMIN_KEY}, json={"target_invoice_id": "INV-P-B31"})
            r_a1_dup = client_d4.post("/api/admin/adjustments/adj_b31_neg/apply", headers={"X-Admin-Key": ADMIN_KEY}, json={"target_invoice_id": "INV-P-B31"})
            r_a2 = client_d4.post("/api/admin/adjustments/adj_b31_pos/apply", headers={"X-Admin-Key": ADMIN_KEY}, json={"target_invoice_id": "INV-P-B31"})
            c_tmp = get_connection(db_d4)
            tot31 = int(c_tmp.execute("SELECT total_cents FROM invoices WHERE id='INV-P-B31'").fetchone()["total_cents"])
            c_tmp.close()
            c_b31.append(("signed_adjustment_credit_subtracts_and_debit_adds", r_a1.status_code == 200 and r_a2.status_code == 200 and tot31 == 48900))
            c_b31.append(("already_applied_adjustment_cannot_be_reapplied", r_a1_dup.status_code == 400 and tot31 == 48900))
        except Exception as e:
            c_b31.append(("bug31_probe", False, str(e)))
        _record_bug(a1_results, weights, "BUG-31", c_b31)

        # ==================================================================
        # 域 5：复式总账与递延摊销链路 (BUG-32 ~ BUG-38)
        # ==================================================================
        db_d5 = _copy_fresh_template_db(tmp_dir, "d5.db")
        app_d5 = _load_delivery_app(delivery_dir, db_d5)
        client_d5 = app_d5.test_client()

        # BUG-32 [潜伏]: 复式总账凭证生成器对存在调账差额（total_cents != 分项之和）的账单仍严格借贷平衡且净应收匹配
        c_b32 = []
        try:
            from app.infra.db import tx_context  # type: ignore

            with tx_context(db_d5, immediate=True) as conn:
                # 构造既有负向减免单又有正向加收单的开放期样本
                conn.execute("UPDATE invoices SET total_cents = 4900 WHERE id = 'INV-202611-0166'")
                conn.execute("UPDATE invoices SET total_cents = 64900 WHERE id = 'INV-202611-0002'")
            r_gl11 = client_d5.get("/api/admin/gl/2026-11", headers={"X-Admin-Key": ADMIN_KEY})
            gl_j = r_gl11.get_json() or {}
            with tx_context(db_d5) as conn:
                dr_sum, cr_sum = conn.execute("SELECT COALESCE(SUM(debit_cents),0), COALESCE(SUM(credit_cents),0) FROM gl_journal_entries WHERE period_key='2026-11'").fetchone()
                ar_net = int(conn.execute(
                    "SELECT COALESCE(SUM(CASE WHEN debit_account LIKE '1122%' THEN debit_cents ELSE 0 END),0) - COALESCE(SUM(CASE WHEN credit_account LIKE '1122%' THEN credit_cents ELSE 0 END),0) FROM gl_journal_entries WHERE period_key='2026-11'"
                ).fetchone()[0])
                from app.infra.db import parse_legacy_amount_cents  # type: ignore

                exp_ar = sum(
                    parse_legacy_amount_cents(dict(r), "total_cents")
                    for r in conn.execute("SELECT * FROM invoices WHERE period_key='2026-11' AND status!='VOID'").fetchall()
                )
            c_b32.append(("gl_journal_trial_balance_strictly_equal_with_adjustments", r_gl11.status_code == 200 and gl_j.get("balanced") is True and int(dr_sum) == int(cr_sum) and int(dr_sum) > 0))
            c_b32.append(("gl_net_accounts_receivable_matches_active_invoices", ar_net == exp_ar))
        except Exception as e:
            c_b32.append(("bug32_probe", False, str(e)))
        _record_bug(a1_results, weights, "BUG-32", c_b32)

        # BUG-33 [潜伏]: 退款触发 invoice.refunded 事件且 ERP 同步队列仅按实退现金写入负数冲销凭证
        c_b33 = []
        try:
            from app.domain.ledger import pay_invoice_from_wallet, refund_to_wallet  # type: ignore
            from app.hooks.erp_sync_hooks import clear_pending_erp_voucher_queue, get_pending_erp_voucher_queue  # type: ignore
            from app.infra.db import tx_context  # type: ignore

            clear_pending_erp_voucher_queue()
            with tx_context(db_d5, immediate=True) as conn:
                conn.execute(
                    """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
                       base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
                       currency_unit, status, created_at, updated_at)
                       VALUES ('INV-P-B33', 't_cust_008', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z',
                       'STARTER', 15000, 0, 0, 0, 15000, 0, 0, 'CENTS', 'OPEN', '2026-11-12T00:00:00Z', '2026-11-12T00:00:00Z')"""
                )
                pay_invoice_from_wallet(conn, "INV-P-B33", "t_cust_008", idempotency_key="idem-b33")
                # 10000 赠金 + 5000 现金；退款 12000 时优先退赠金 10000 + 实退现金 2000（或先退现金 5000？注意权威规范：混合支付退款先退赠送金或按原比例？见 wallet_bridge/ledger）
                ref_res = refund_to_wallet(conn, "INV-P-B33", 12000, reason="erp_hook_probe")
            q = [x for x in get_pending_erp_voucher_queue() if x.get("invoice_id") == "INV-P-B33" and x.get("kind") == "REFUND_REVERSAL"]
            expected_cash_ref = int(ref_res.get("cash_refunded_cents", 0))
            c_b33.append(("refund_publishes_event_to_erp_sync_queue", len(q) == 1))
            c_b33.append(("erp_refund_reversal_records_negative_cash_refund_only", len(q) == 1 and int(q[0].get("amount_cents", 0)) == -expected_cash_ref and expected_cash_ref < 0 or (len(q) == 1 and expected_cash_ref > 0 and int(q[0].get("amount_cents", 0)) == -expected_cash_ref)))
        except Exception as e:
            c_b33.append(("bug33_probe", False, str(e)))
        _record_bug(a1_results, weights, "BUG-33", c_b33)

        # BUG-34: 多月预付递延收入剥离含税销项税/价外税且余数尾差补齐末期（总额守恒、末期递延归零）
        c_b34 = []
        try:
            r_sc1 = client_d5.post("/api/admin/analytics/asc606/schedule", headers={"X-Admin-Key": ADMIN_KEY}, json={"invoice_id": "INV-202611-0219", "contract_months": 3})
            r_sc2 = client_d5.post("/api/admin/analytics/asc606/schedule", headers={"X-Admin-Key": ADMIN_KEY}, json={"invoice_id": "INV-202611-0220", "contract_months": 3})
            j1 = r_sc1.get_json() or {}
            j2 = r_sc2.get_json() or {}
            c_b34.append(("asc606_strips_inclusive_vat_from_revenue_pool", r_sc1.status_code == 200 and j1.get("target_net_revenue_cents") == 56321 and j1.get("scheduled_sum_cents") == 56321))
            c_b34.append(("asc606_allocates_remainder_so_ending_deferred_is_zero", r_sc2.status_code == 200 and j2.get("scheduled_sum_cents") == 100000 and j2.get("ending_deferred_cents") == 0))
        except Exception as e:
            c_b34.append(("bug34_probe", False, str(e)))
        _record_bug(a1_results, weights, "BUG-34", c_b34)

        # BUG-35 [潜伏]: 期中升配重排递延收入摊销表采用未来适用法，绝不篡改已关账历史月份
        c_b35 = []
        try:
            from app.infra.db import get_connection  # type: ignore

            r_reb = client_d5.post(
                "/api/admin/analytics/asc606/rebaseline",
                headers={"X-Admin-Key": ADMIN_KEY},
                json={"invoice_id": "INV-202610-0028", "added_net_cents": 30000, "modification_period_key": "2026-11"},
            )
            c_tmp = get_connection(db_d5)
            rows35 = c_tmp.execute("SELECT period_key, recognized_cents, deferred_closing_cents, status FROM deferred_revenue_schedules WHERE invoice_id='INV-202610-0028' ORDER BY period_key ASC").fetchall()
            c_tmp.close()
            by_p = {r["period_key"]: dict(r) for r in rows35}
            c_b35.append(("historical_recognized_period_frozen_on_upgrade", r_reb.status_code == 200 and by_p.get("2026-10", {}).get("recognized_cents") == 62862))
            c_b35.append((
                "prospective_periods_absorb_added_consideration_conservatively",
                sum(int(r["recognized_cents"]) for r in rows35) == 188585 + 30000 and by_p.get("2026-12", {}).get("deferred_closing_cents") == 0,
            ))
        except Exception as e:
            c_b35.append(("bug35_probe", False, str(e)))
        _record_bug(a1_results, weights, "BUG-35", c_b35)

        # BUG-36 [潜伏]: 赠送金合同负债滚存底稿计入 REFUND 退回赠金流水，期末余额与钱包快照平齐
        c_b36 = []
        try:
            from app.finance_recon_hub.promo_liability_rollforward import compute_promo_wallet_rollforward  # type: ignore
            from app.infra.db import tx_context  # type: ignore

            with tx_context(db_d5, immediate=True) as conn:
                # 在干净测试环境中让 wallets.promo_balance_cents 严格等于全部 wallet_ledger.promo_delta_cents 之和（含正数 REFUND）
                conn.execute("UPDATE wallets SET promo_balance_cents = 0")
                conn.execute(
                    """UPDATE wallets SET promo_balance_cents = COALESCE((
                           SELECT SUM(promo_delta_cents) FROM wallet_ledger l WHERE l.tenant_id = wallets.tenant_id
                       ), 0)"""
                )
                conn.execute(
                    """INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at)
                       VALUES ('t_cust_008', 'REFUND', 0, 3500, 'INV-P-B36', '退券测试', '2026-11-12T00:00:00Z')"""
                )
                conn.execute("UPDATE wallets SET promo_balance_cents = promo_balance_cents + 3500 WHERE tenant_id = 't_cust_008'")
                rf = compute_promo_wallet_rollforward(conn)
            c_b36.append(("promo_rollforward_includes_refund_restored_credits", rf["ledger_vs_wallet_reconciled"] is True and rf["cumulative_promo_refund_restored_cents"] >= 3500))
        except Exception as e:
            c_b36.append(("bug36_probe", False, str(e)))
        _record_bug(a1_results, weights, "BUG-36", c_b36)

        # BUG-37 [潜伏]: 话单-账单-总账三方勾稽底稿消除多分段汇总行 LEFT JOIN 笛卡尔膨胀
        c_b37 = []
        try:
            from app.finance_recon_hub.three_way_cdr_bill_gl import build_period_three_way_tieout  # type: ignore
            from app.infra.db import tx_context  # type: ignore

            with tx_context(db_d5, immediate=True) as conn:
                tie = build_period_three_way_tieout(conn, "2026-11")
            b_leg = tie.get("billing_leg", {})
            c_b37.append((
                "three_way_tieout_no_cartesian_join_fanout",
                b_leg.get("billing_join_tieout_matched") is True and b_leg.get("joined_crosscheck_cents") == b_leg.get("invoice_gross_total_cents"),
            ))
        except Exception as e:
            c_b37.append(("bug37_probe", False, str(e)))
        _record_bug(a1_results, weights, "BUG-37", c_b37)

        # BUG-38: 中国境内增值税申报底稿剔除新加坡 SG_GST_9_EXCLUSIVE 境外税额
        c_b38 = []
        try:
            r_vat = client_d5.get("/api/admin/analytics/vat-workpaper/2026-10", headers={"X-Admin-Key": ADMIN_KEY})
            vj = r_vat.get_json() or {}
            by_tp = vj.get("by_tax_profile", {})
            expected_prc_vat = int(by_tp.get("CN_VAT_6_INCLUSIVE", {}).get("output_vat_cents", 0)) + int(by_tp.get("CN_VAT_6_EXCLUSIVE", {}).get("output_vat_cents", 0))
            sg_vat = int(by_tp.get("SG_GST_9_EXCLUSIVE", {}).get("output_vat_cents", 0))
            c_b38.append(("prc_vat_workpaper_excludes_singapore_gst", r_vat.status_code == 200 and sg_vat > 0 and vj.get("prc_total_output_vat_cents") == expected_prc_vat))
        except Exception as e:
            c_b38.append(("bug38_probe", False, str(e)))
        _record_bug(a1_results, weights, "BUG-38", c_b38)

        # ==================================================================
        # 域 6：渠道分润与催收内控链路 (BUG-39 ~ BUG-50)
        # ==================================================================
        db_d6 = _copy_fresh_template_db(tmp_dir, "d6.db")
        app_d6 = _load_delivery_app(delivery_dir, db_d6)
        client_d6 = app_d6.test_client()

        # BUG-39 / BUG-40 / BUG-41 / BUG-43: 渠道返佣跨月退款扣回 + 负向冲抵保留 + 实收现金动态评级 + 保护 PAID_OUT + 绑定时间窗过滤
        c_b39, c_b40, c_b41, c_b43 = [], [], [], []
        try:
            from app.infra.db import get_connection, tx_context  # type: ignore

            # 先篡改 2026-10 已打款单的哨兵金额，验证重算 2026-10 时不会覆写 PAID_OUT 行
            with tx_context(db_d6, immediate=True) as conn:
                conn.execute("UPDATE partner_commissions SET commission_cents = 7777 WHERE id = 'pc_202610_PTN_SOUTH' AND status = 'PAID_OUT'")
            r_ptn10 = client_d6.get("/api/partners/commissions?period_key=2026-10", headers={"X-Admin-Key": ADMIN_KEY})
            c_tmp = get_connection(db_d6)
            p10_south = c_tmp.execute("SELECT commission_cents, status FROM partner_commissions WHERE id = 'pc_202610_PTN_SOUTH'").fetchone()
            c_tmp.close()
            c_b41.append(("paid_out_partner_commission_immutable_on_recalc", r_ptn10.status_code == 200 and p10_south["status"] == "PAID_OUT" and int(p10_south["commission_cents"]) == 7777))

            r_tier = client_d6.get("/api/partners/tier-eval?partner_code=PTN_SOUTH&period_key=2026-11&base_tier=SILVER", headers={"X-Admin-Key": ADMIN_KEY})
            tj = r_tier.get_json() or {}
            c_b40.append(("partner_quarterly_tier_uses_net_collected_cash_not_unpaid_gross", r_tier.status_code == 200 and tj.get("effective_tier") == "SILVER" and int(tj.get("evaluated_basis_cents", -1)) < 500000))

            r_ptn11 = client_d6.get("/api/partners/commissions?period_key=2026-11", headers={"X-Admin-Key": ADMIN_KEY})
            comm_map = {x["partner_code"]: x for x in (r_ptn11.get_json() or {}).get("commissions", [])}
            south11 = comm_map.get("PTN_SOUTH", {})
            c_b39.append(("clawback_tracks_refund_event_month_and_preserves_negative_offset", int(south11.get("net_cash_collected_cents", 999)) == -120000 and int(south11.get("commission_cents", 999)) == -9600))

            # 再验证绑定时间窗：t_cust_022 在 2026-11-10 绑定 PTN_SOUTH，11-02 的 59900 回款必须被剔除；若在 11-12 新增一笔 10000 现金回款则应被计入 (-120000 + 10000 = -110000)
            with tx_context(db_d6, immediate=True) as conn:
                conn.execute(
                    """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
                       base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
                       currency_unit, status, created_at, updated_at)
                       VALUES ('INV-POST-BIND-22', 't_cust_022', '2026-11', '2026-11-11T00:00:00Z', '2026-12-11T00:00:00Z',
                       'STARTER', 10000, 0, 0, 0, 10000, 10000, 0, 'CENTS', 'PAID', '2026-11-12T00:00:00Z', '2026-11-12T00:00:00Z')"""
                )
                conn.execute(
                    """INSERT INTO invoice_payments (id, invoice_id, tenant_id, idempotency_key, cash_paid_cents, promo_paid_cents, total_paid_cents, created_at)
                       VALUES ('pay_post_bind_22', 'INV-POST-BIND-22', 't_cust_022', 'idem_pb22', 10000, 0, 10000, '2026-11-12T01:00:00Z')"""
                )
            r_ptn11_b = client_d6.get("/api/partners/commissions?period_key=2026-11", headers={"X-Admin-Key": ADMIN_KEY})
            south11_b = {x["partner_code"]: x for x in (r_ptn11_b.get_json() or {}).get("commissions", [])}.get("PTN_SOUTH", {})
            c_b43.append(("referral_attribution_excludes_pre_bound_and_includes_post_bound_payments", int(south11.get("net_cash_collected_cents", 999)) == -120000 and int(south11_b.get("net_cash_collected_cents", 999)) == -110000))
        except Exception as e:
            err_s = str(e)
            c_b39.append(("bug39_probe", False, err_s))
            c_b40.append(("bug40_probe", False, err_s))
            c_b41.append(("bug41_probe", False, err_s))
            c_b43.append(("bug43_probe", False, err_s))
        _record_bug(a1_results, weights, "BUG-39", c_b39)
        _record_bug(a1_results, weights, "BUG-40", c_b40)
        _record_bug(a1_results, weights, "BUG-41", c_b41)
        _record_bug(a1_results, weights, "BUG-43", c_b43)

        # BUG-42 [潜伏]: 总代与二级子代理按级差 max(0, parent_bps - child_bps) 计提管理津贴
        c_b42 = []
        try:
            r_sub = client_d6.get("/api/partners/sub-split?period_key=2026-11", headers={"X-Admin-Key": ADMIN_KEY})
            sj = r_sub.get_json() or {}
            sp_map = {x["child_partner_code"]: x for x in sj.get("splits", [])}
            s1 = sp_map.get("PTN_SOUTH_SUB1", {})
            # PTN_EAST (1200 bps) -> PTN_SOUTH_SUB1 (800 bps), net_cash = 199900: child = 15992 (8%), parent override = 7996 (4% 级差), combined = 23988 (12%)
            c_b42.append((
                "parent_distributor_override_uses_rate_differential",
                r_sub.status_code == 200 and s1.get("child_commission_cents") == 15992 and s1.get("parent_override_cents") == 7996 and s1.get("combined_payout_cents") == 23988,
            ))
        except Exception as e:
            c_b42.append(("bug42_probe", False, str(e)))
        _record_bug(a1_results, weights, "BUG-42", c_b42)

        # BUG-44 & BUG-46: 逾期催收跳过争议冻结账单不误停机 + 每日跑批 5% 滞纳金按未付本金单次幂等计提不复利叠加
        c_b44, c_b46 = [], []
        try:
            from app.infra.db import get_connection, tx_context  # type: ignore
            from app.jobs.dunning_escalation_job import run_dunning_escalation_job  # type: ignore

            with tx_context(db_d6, immediate=True) as conn:
                # 构造争议中逾期 >35 天的活跃租户 t_cust_009 与部分已付逾期单 t_cust_008
                conn.execute(
                    """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
                       base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
                       currency_unit, status, dispute_reason, created_at, updated_at)
                       VALUES ('INV-DUN-DISP', 't_cust_009', '2026-11', '2026-09-25T00:00:00Z', '2026-10-05T00:00:00Z',
                       'PRO', 59900, 0, 0, 0, 59900, 0, 0, 'CENTS', 'OPEN', '核对账单争议冻结', '2026-10-05T00:00:00Z', '2026-11-01T00:00:00Z')"""
                )
                conn.execute(
                    "INSERT INTO dispute_tickets (id, invoice_id, tenant_id, reason, freeze_auto_debit, status, created_at) VALUES ('dsp_dun_09', 'INV-DUN-DISP', 't_cust_009', '争议核账', 1, 'OPEN', '2026-11-01T00:00:00Z')"
                )
                conn.execute(
                    """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
                       base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
                       currency_unit, status, dispute_reason, created_at, updated_at)
                       VALUES ('INV-DUN-PART', 't_cust_008', '2026-11', '2026-10-01T00:00:00Z', '2026-11-01T00:00:00Z',
                       'ENTERPRISE', 100000, 0, 0, 0, 100000, 40000, 0, 'CENTS', 'OPEN', '', '2026-11-01T00:00:00Z', '2026-11-01T00:00:00Z')"""
                )
                run_dunning_escalation_job(conn, "2026-11-14T00:00:00Z")
                run_dunning_escalation_job(conn, "2026-11-15T00:00:00Z")
            c_tmp = get_connection(db_d6)
            t09_st = c_tmp.execute("SELECT status FROM tenants WHERE id='t_cust_009'").fetchone()["status"]
            inv_disp = c_tmp.execute("SELECT late_fee_cents, total_cents FROM invoices WHERE id='INV-DUN-DISP'").fetchone()
            inv_part = c_tmp.execute("SELECT late_fee_cents, total_cents FROM invoices WHERE id='INV-DUN-PART'").fetchone()
            c_tmp.close()
            c_b44.append(("disputed_overdue_invoice_exempt_from_dunning_and_suspension", t09_st == "ACTIVE" and int(inv_disp["late_fee_cents"]) == 0))
            # 未付本金 60000 * 5% = 3000，连续跑批两次仍严格保持 late_fee=3000, total=103000
            c_b46.append(("late_fee_accrued_once_on_unpaid_principal_without_compounding", int(inv_part["late_fee_cents"]) == 3000 and int(inv_part["total_cents"]) == 103000))
        except Exception as e:
            err_s = str(e)
            c_b44.append(("bug44_probe", False, err_s))
            c_b46.append(("bug46_probe", False, err_s))
        _record_bug(a1_results, weights, "BUG-44", c_b44)
        _record_bug(a1_results, weights, "BUG-46", c_b46)

        # BUG-45: 欠费停机租户缴清全部逾期欠款后自动复机 ACTIVE（若仍有其他未结清逾期单则保持 SUSPENDED）
        c_b45 = []
        try:
            from app.infra.db import get_connection, tx_context  # type: ignore

            with tx_context(db_d6, immediate=True) as conn:
                conn.execute("UPDATE tenants SET status = 'SUSPENDED' WHERE id = 't_cust_012'")
                conn.execute("UPDATE subscriptions SET status = 'SUSPENDED' WHERE tenant_id = 't_cust_012'")
                conn.execute("UPDATE wallets SET cash_balance_cents = 500000 WHERE tenant_id = 't_cust_012'")
                conn.execute(
                    """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
                       base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
                       currency_unit, status, created_at, updated_at)
                       VALUES ('INV-REACT-1', 't_cust_012', '2026-11', '2026-10-01T00:00:00Z', '2026-11-01T00:00:00Z',
                       'PRO', 59900, 0, 0, 0, 59900, 0, 0, 'CENTS', 'OVERDUE', '2026-11-01T00:00:00Z', '2026-11-01T00:00:00Z')"""
                )
                conn.execute(
                    """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
                       base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
                       currency_unit, status, created_at, updated_at)
                       VALUES ('INV-REACT-2', 't_cust_012', '2026-11', '2026-10-01T00:00:00Z', '2026-11-01T00:00:00Z',
                       'PRO', 59900, 0, 0, 0, 59900, 0, 0, 'CENTS', 'OPEN', '2026-11-01T00:00:00Z', '2026-11-01T00:00:00Z')"""
                )
            # 先付第 1 张，因第 2 张已过 cycle_end 仍逾期未付，必须保持 SUSPENDED
            client_d6.post("/api/invoices/INV-REACT-1/pay", headers={"X-Tenant-Token": "tok_cust_012", "Idempotency-Key": "react-1"})
            c_tmp = get_connection(db_d6)
            st_mid = c_tmp.execute("SELECT status FROM tenants WHERE id='t_cust_012'").fetchone()["status"]
            c_tmp.close()
            # 再付清第 2 张，所有逾期账单全部结清，租户与订阅均自动恢复 ACTIVE
            client_d6.post("/api/invoices/INV-REACT-2/pay", headers={"X-Tenant-Token": "tok_cust_012", "Idempotency-Key": "react-2"})
            c_tmp = get_connection(db_d6)
            st_end = c_tmp.execute("SELECT status FROM tenants WHERE id='t_cust_012'").fetchone()["status"]
            sub_end = c_tmp.execute("SELECT status FROM subscriptions WHERE tenant_id='t_cust_012'").fetchone()["status"]
            c_tmp.close()
            c_b45.append(("keeps_suspended_while_other_overdue_invoices_remain", st_mid == "SUSPENDED"))
            c_b45.append(("reactivates_tenant_and_subscription_once_all_overdue_cleared", st_end == "ACTIVE" and sub_end == "ACTIVE"))
        except Exception as e:
            c_b45.append(("bug45_probe", False, str(e)))
        _record_bug(a1_results, weights, "BUG-45", c_b45)

        # BUG-47: 双人四眼审批大小写与空白归一化防自审 + decision 严格白名单 ('APPROVE', 'REJECT')
        c_b47 = []
        try:
            r_cr = client_d6.post(
                "/api/admin/approvals",
                headers={"X-Admin-Key": ADMIN_KEY},
                json={"ticket_type": "LARGE_REFUND_CHECK", "tenant_id": "t_cust_015", "ref_object_id": "INV-202611-0015", "amount_cents": 600000, "requested_by": "ops_alice", "reason": "probe_47"},
            )
            tid47 = (r_cr.get_json() or {}).get("id", "")
            r_self1 = client_d6.post(f"/api/admin/approvals/{tid47}/decide", headers={"X-Admin-Key": ADMIN_KEY}, json={"approver": " Ops_Alice ", "decision": "APPROVE"})
            r_hold = client_d6.post(f"/api/admin/approvals/{tid47}/decide", headers={"X-Admin-Key": ADMIN_KEY}, json={"approver": "fin_bob", "decision": "HOLD"})
            r_ok1 = client_d6.post(f"/api/admin/approvals/{tid47}/decide", headers={"X-Admin-Key": ADMIN_KEY}, json={"approver": "fin_bob", "decision": "APPROVE"})
            r_self2 = client_d6.post(f"/api/admin/approvals/{tid47}/decide", headers={"X-Admin-Key": ADMIN_KEY}, json={"approver": "FIN_BOB ", "decision": "APPROVE"})
            r_self_maker2 = client_d6.post(f"/api/admin/approvals/{tid47}/decide", headers={"X-Admin-Key": ADMIN_KEY}, json={"approver": "OPS_ALICE", "decision": "APPROVE"})
            r_ok2 = client_d6.post(f"/api/admin/approvals/{tid47}/decide", headers={"X-Admin-Key": ADMIN_KEY}, json={"approver": "cfo_carol", "decision": "APPROVE"})
            c_b47.append((
                "case_whitespace_normalized_sod_blocks_maker_and_same_signer",
                r_self1.status_code in (400, 403) and r_self2.status_code in (400, 403) and r_self_maker2.status_code in (400, 403) and r_ok1.status_code == 200 and r_ok2.status_code == 200,
            ))
            c_b47.append(("invalid_decision_keyword_rejected_not_auto_approved", r_hold.status_code == 400))
        except Exception as e:
            c_b47.append(("bug47_probe", False, str(e)))
        _record_bug(a1_results, weights, "BUG-47", c_b47)

        # BUG-48: 单笔满 5,000 元 (>= 500,000 分) 退费与调账核销强制要求终审通过 APPROVED 审批单
        c_b48 = []
        try:
            from app.infra.db import tx_context  # type: ignore

            with tx_context(db_d6, immediate=True) as conn:
                conn.execute(
                    """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
                       base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
                       currency_unit, status, created_at, updated_at)
                       VALUES ('INV-WHALE-48', 't_cust_015', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z',
                       'ENTERPRISE', 700000, 0, 0, 0, 700000, 700000, 0, 'CENTS', 'PAID', '2026-11-12T00:00:00Z', '2026-11-12T00:00:00Z')"""
                )
                conn.execute(
                    """INSERT INTO invoice_payments (id, invoice_id, tenant_id, idempotency_key, cash_paid_cents, promo_paid_cents, total_paid_cents, created_at)
                       VALUES ('pay_whale_48', 'INV-WHALE-48', 't_cust_015', 'idem_w48', 700000, 0, 700000, '2026-11-12T00:05:00Z')"""
                )
                conn.execute(
                    """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
                       base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
                       currency_unit, status, created_at, updated_at)
                       VALUES ('INV-ADJ-48', 't_cust_015', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z',
                       'ENTERPRISE', 700000, 0, 0, 0, 700000, 0, 0, 'CENTS', 'OPEN', '2026-11-12T00:00:00Z', '2026-11-12T00:00:00Z')"""
                )
                conn.execute(
                    """INSERT INTO billing_adjustments (id, tenant_id, ref_invoice_id, target_period_key, applied_period_key,
                       adjustment_type, delta_cents, reason, status, created_at)
                       VALUES ('adj_whale_48', 't_cust_015', 'INV-202610-0015', '2026-10', '2026-11',
                       'CREDIT_MEMO', -520000, '大额减免需双签', 'PENDING', '2026-11-13T00:00:00Z')"""
                )
            # 无审批单或传 FIRST_APPROVED 未终审单 apv_2026_0004 必须被拦截
            r_ref_no = client_d6.post("/api/invoices/INV-WHALE-48/refund", headers={"X-Admin-Key": ADMIN_KEY}, json={"refund_cents": 500000, "reason": "no_ticket"})
            r_ref_half = client_d6.post("/api/invoices/INV-WHALE-48/refund", headers={"X-Admin-Key": ADMIN_KEY}, json={"refund_cents": 500000, "reason": "half_ticket", "approval_ticket_id": "apv_2026_0004"})
            r_adj_no = client_d6.post("/api/admin/adjustments/adj_whale_48/apply", headers={"X-Admin-Key": ADMIN_KEY}, json={"target_invoice_id": "INV-ADJ-48"})

            # 创建并完成双人异号终审后放行
            t_ref = (client_d6.post("/api/admin/approvals", headers={"X-Admin-Key": ADMIN_KEY}, json={"ticket_type": "LARGE_REFUND_CHECK", "tenant_id": "t_cust_015", "ref_object_id": "INV-WHALE-48", "amount_cents": 500000, "requested_by": "cs_01", "reason": "ok"}).get_json() or {})["id"]
            client_d6.post(f"/api/admin/approvals/{t_ref}/decide", headers={"X-Admin-Key": ADMIN_KEY}, json={"approver": "fin_1", "decision": "APPROVE"})
            client_d6.post(f"/api/admin/approvals/{t_ref}/decide", headers={"X-Admin-Key": ADMIN_KEY}, json={"approver": "cfo_2", "decision": "APPROVE"})
            r_ref_ok = client_d6.post("/api/invoices/INV-WHALE-48/refund", headers={"X-Admin-Key": ADMIN_KEY}, json={"refund_cents": 500000, "reason": "approved", "approval_ticket_id": t_ref})

            t_adj = (client_d6.post("/api/admin/approvals", headers={"X-Admin-Key": ADMIN_KEY}, json={"ticket_type": "CREDIT_ADJUSTMENT", "tenant_id": "t_cust_015", "ref_object_id": "adj_whale_48", "amount_cents": 520000, "requested_by": "cs_01", "reason": "ok"}).get_json() or {})["id"]
            client_d6.post(f"/api/admin/approvals/{t_adj}/decide", headers={"X-Admin-Key": ADMIN_KEY}, json={"approver": "fin_1", "decision": "APPROVE"})
            client_d6.post(f"/api/admin/approvals/{t_adj}/decide", headers={"X-Admin-Key": ADMIN_KEY}, json={"approver": "cfo_2", "decision": "APPROVE"})
            r_adj_ok = client_d6.post("/api/admin/adjustments/adj_whale_48/apply", headers={"X-Admin-Key": ADMIN_KEY}, json={"target_invoice_id": "INV-ADJ-48", "approval_ticket_id": t_adj})

            c_b48.append(("high_value_refund_enforces_approved_dual_sign_ticket", r_ref_no.status_code in (400, 403) and r_ref_half.status_code in (400, 403) and r_ref_ok.status_code == 200))
            c_b48.append(("high_value_adjustment_enforces_approved_dual_sign_ticket", r_adj_no.status_code in (400, 403) and r_adj_ok.status_code == 200))
        except Exception as e:
            c_b48.append(("bug48_probe", False, str(e)))
        _record_bug(a1_results, weights, "BUG-48", c_b48)

        # BUG-49 [潜伏]: SOX 内控合规巡检检出大小写/空白归一化的一审自批及同人双签违规样本 (apv_sod_leak_01)
        c_b49 = []
        try:
            r_sox = client_d6.get("/api/admin/diagnostics/sox-controls", headers={"X-Admin-Key": ADMIN_KEY})
            sox_j = r_sox.get_json() or {}
            c06 = next((c for c in sox_j.get("controls", []) if c.get("control_id") == "SOX-FIN-06"), {})
            c_b49.append(("sox_sod_detector_catches_first_approver_case_whitespace_self_approval", r_sox.status_code == 200 and int(c06.get("sod_violations", 0)) >= 1))
        except Exception as e:
            c_b49.append(("bug49_probe", False, str(e)))
        _record_bug(a1_results, weights, "BUG-49", c_b49)

        # BUG-50 [潜伏]: 并发会签请求使用 IMMEDIATE 锁与乐观状态更新，防止同一审批人并发穿透一审与二审
        c_b50 = []
        try:
            db_b50 = _copy_fresh_template_db(tmp_dir, "b50.db")
            app_b50 = _load_delivery_app(delivery_dir, db_b50)
            from app.infra.db import get_connection  # type: ignore

            cr50 = app_b50.test_client().post(
                "/api/admin/approvals",
                headers={"X-Admin-Key": ADMIN_KEY},
                json={"ticket_type": "LARGE_REFUND_CHECK", "tenant_id": "t_cust_015", "ref_object_id": "INV-50", "amount_cents": 650000, "requested_by": "maker_50", "reason": "race_50"},
            )
            tid50 = (cr50.get_json() or {})["id"]
            import time as _t50
            import app.services.approval_workflow_service as _aws50  # type: ignore

            _orig_get50 = _aws50.get_approval_ticket

            def _slow_get50(c, tid):
                res = _orig_get50(c, tid)
                _t50.sleep(0.03)
                return res

            _aws50.get_approval_ticket = _slow_get50
            bar50 = threading.Barrier(2)

            def _dec50(_i: int):
                cl50 = app_b50.test_client()
                bar50.wait(timeout=5)
                return cl50.post(
                    f"/api/admin/approvals/{tid50}/decide",
                    headers={"X-Admin-Key": ADMIN_KEY},
                    json={"approver": "same_reviewer", "decision": "APPROVE"},
                ).status_code

            try:
                with ThreadPoolExecutor(max_workers=2) as ex:
                    sts50 = list(ex.map(_dec50, range(2)))
            finally:
                _aws50.get_approval_ticket = _orig_get50
            c50 = get_connection(db_b50)
            row50 = c50.execute("SELECT status, first_approver, second_approver FROM approval_tickets WHERE id=?", (tid50,)).fetchone()
            c50.close()
            c_b50.append((
                "concurrent_same_approver_cannot_advance_past_first_approved",
                row50["status"] == "FIRST_APPROVED" and row50["second_approver"] is None and sts50.count(200) == 1,
            ))
        except Exception as e:
            c_b50.append(("bug50_probe", False, str(e)))
        _record_bug(a1_results, weights, "BUG-50", c_b50)

        # ==================================================================
        # 域 7：安全导出前端与开放期平账链路 (BUG-51 ~ BUG-60)
        # ==================================================================
        db_d7 = _copy_fresh_template_db(tmp_dir, "d7.db")
        app_d7 = _load_delivery_app(delivery_dir, db_d7)
        client_d7 = app_d7.test_client()

        # BUG-51: 账单详情/争议/结算预览横向越权 IDOR 拦截 + 后台 jobs/export 强制管理员鉴权
        c_b51 = []
        try:
            h_att = {"X-Tenant-Token": "tok_cust_008"}
            r_det = client_d7.get("/api/invoices/INV-202611-0004", headers=h_att)
            r_prv = client_d7.get("/api/invoices/INV-202611-0004/settlement-preview", headers=h_att)
            r_dsp = client_d7.post("/api/invoices/INV-202611-0004/dispute", headers=h_att, json={"reason": "idor_attack"})
            r_job_no = client_d7.post("/api/admin/jobs/run")
            r_exp_no = client_d7.get("/api/admin/reconcile/export")
            r_exp_ok = client_d7.get("/api/admin/reconcile/export?period_key=2026-10", headers={"X-Admin-Key": ADMIN_KEY})
            c_b51.append(("idor_blocked_on_detail_preview_and_dispute", r_det.status_code == 403 and r_prv.status_code == 403 and r_dsp.status_code == 403))
            c_b51.append(("admin_jobs_and_export_require_admin_auth", r_job_no.status_code in (401, 403) and r_exp_no.status_code in (401, 403) and r_exp_ok.status_code == 200))
        except Exception as e:
            c_b51.append(("bug51_probe", False, str(e)))
        _record_bug(a1_results, weights, "BUG-51", c_b51)

        # BUG-52: 导出路径防双写/反斜杠穿越 + 异常处理器不泄露堆栈且保留 404/405 HTTP 状态码
        c_b52 = []
        try:
            adm_h = {"X-Admin-Key": ADMIN_KEY}
            r_tr1 = client_d7.get("/api/admin/reconcile/export?file=....//....//README.md", headers=adm_h)
            r_tr2 = client_d7.get("/api/admin/reconcile/export?file=..\\..\\README.md", headers=adm_h)
            r_404 = client_d7.get("/api/non-existent-route-probe-52")
            r_405 = client_d7.delete("/health")

            app_b52 = _load_delivery_app(delivery_dir, db_d7)

            @app_b52.route("/api/_probe_boom_52")
            def _boom52():
                raise RuntimeError("secret_internal_db_path_boom")

            r_500 = app_b52.test_client().get("/api/_probe_boom_52")
            txt500 = r_500.get_data(as_text=True)
            c_b52.append(("path_traversal_double_dot_and_backslash_blocked", r_tr1.status_code in (400, 403) and r_tr2.status_code in (400, 403)))
            c_b52.append((
                "error_handler_hides_traceback_and_preserves_http_404_405",
                r_404.status_code == 404 and r_405.status_code == 405 and r_500.status_code == 500 and "Traceback" not in txt500 and "secret_internal_db_path_boom" not in txt500,
            ))
        except Exception as e:
            c_b52.append(("bug52_probe", False, str(e)))
        _record_bug(a1_results, weights, "BUG-52", c_b52)

        # BUG-53 [潜伏]: Webhook 验签使用 compare_digest 并拒绝超 300 秒重放 + 连续失败 >=5 次转 DEAD_LETTER
        c_b53 = []
        try:
            import inspect
            from app.infra import security as sec_mod  # type: ignore
            from app.infra.db import get_connection  # type: ignore

            body_s = '{"event":"invoice.paid","id":"wh_1"}'
            sig_ok = sec_mod.sign_webhook_payload("1763000000", body_s)
            v_fresh = sec_mod.verify_webhook_signature("1763000000", body_s, sig_ok, now_epoch=1763000120.0)
            v_stale = sec_mod.verify_webhook_signature("1763000000", body_s, sig_ok, now_epoch=1763000450.0)
            v_future = sec_mod.verify_webhook_signature("1763000900", body_s, sec_mod.sign_webhook_payload("1763000900", body_s), now_epoch=1763000000.0)
            uses_cd = "compare_digest" in inspect.getsource(sec_mod.verify_webhook_signature)
            c_b53.append(("webhook_sig_uses_compare_digest_and_300s_replay_window", uses_cd and v_fresh is True and v_stale is False and v_future is False))

            # wh_poison_025 在模板库中 attempts=4, status='QUEUED'，再调度一次满 5 次必须置为 DEAD_LETTER
            r_wh = client_d7.post("/api/admin/webhooks/dispatch", headers={"X-Admin-Key": ADMIN_KEY})
            c_tmp = get_connection(db_d7)
            wh_r = c_tmp.execute("SELECT delivery_status, attempts FROM webhook_outbox WHERE id='wh_poison_025'").fetchone()
            c_tmp.close()
            c_b53.append(("poison_webhook_moved_to_dead_letter_at_5_attempts", r_wh.status_code == 200 and wh_r["delivery_status"] == "DEAD_LETTER" and int(wh_r["attempts"]) >= 5))
        except Exception as e:
            c_b53.append(("bug53_probe", False, str(e)))
        _record_bug(a1_results, weights, "BUG-53", c_b53)

        # BUG-54 [潜伏]: 请求中间件不累积 event_bus 订阅 + 独立审计异常关闭 SQLite 连接 + 限流器清理过期桶不无限膨胀
        c_b54 = []
        try:
            from app.infra.events import event_bus  # type: ignore
            from app.infra.rate_limiter import SlidingWindowRateLimiter  # type: ignore
            import app.services.report_export_service as rep_svc  # type: ignore

            sub0 = len(event_bus._subscribers.get("invoice.paid", []))
            for _ in range(15):
                client_d7.get("/health")
            sub1 = len(event_bus._subscribers.get("invoice.paid", []))
            c_b54.append(("no_per_request_event_bus_listener_leak", sub1 <= sub0))

            orig_conn = rep_svc.sqlite3.connect
            stats = {"open": 0, "close": 0}

            class _ProxyConn:
                def __init__(self, rc):
                    self._rc = rc
                    stats["open"] += 1

                def close(self):
                    stats["close"] += 1
                    return self._rc.close()

                def __enter__(self):
                    self._rc.__enter__()
                    return self

                def __exit__(self, *a):
                    return self._rc.__exit__(*a)

                def __getattr__(self, k):
                    return getattr(self._rc, k)

            rep_svc.sqlite3.connect = lambda *a, **kw: _ProxyConn(orig_conn(*a, **kw))  # type: ignore
            try:
                r_bad_p = client_d7.get("/api/admin/reports/standalone-audit/INVALID_PERIOD", headers={"X-Admin-Key": ADMIN_KEY})
            finally:
                rep_svc.sqlite3.connect = orig_conn  # type: ignore

            rl = SlidingWindowRateLimiter(window_seconds=0)
            for idx in range(50):
                rl.check_and_record(f"ephemeral_{idx}", "STARTER")
            rl.check_and_record("active_last", "STARTER")
            c_b54.append((
                "db_closed_on_error_and_rate_limiter_evicts_expired_state",
                r_bad_p.status_code == 400 and stats["open"] == stats["close"] and rl.tracked_bucket_count() <= 5,
            ))
        except Exception as e:
            c_b54.append(("bug54_probe", False, str(e)))
        _record_bug(a1_results, weights, "BUG-54", c_b54)

        # BUG-55 [潜伏]: CSV 导出转义公式注入前缀 (=,+,-,@) 但保留纯数字负数 + 分页导出稳定排序跨页不重不漏
        c_b55 = []
        try:
            from app.infra.db import tx_context  # type: ignore
            from app.utils.csv_parser import format_records_to_csv  # type: ignore

            csv_inj = format_records_to_csv(
                [{"company_name": "=CMD|' /C calc'!A0", "note": "@SUM(1+1)", "delta_cents": -15000}],
                ["company_name", "note", "delta_cents"],
            )
            lines_inj = csv_inj.strip().splitlines()
            c_b55.append((
                "csv_escapes_formula_injection_while_preserving_negative_numbers",
                "'=CMD" in lines_inj[1] and "'@SUM" in lines_inj[1] and lines_inj[1].endswith(",-15000"),
            ))

            with tx_context(db_d7, immediate=True) as conn:
                conn.execute("UPDATE invoices SET created_at = '2026-11-01T00:00:00Z' WHERE period_key = '2026-11'")
                total_nov_cnt = int(conn.execute("SELECT COUNT(*) FROM invoices WHERE period_key='2026-11'").fetchone()[0])
            seen_ids = []
            for pg in range(1, (total_nov_cnt // 25) + 3):
                r_pg = client_d7.get(f"/api/admin/reports/invoices-page.csv?period_key=2026-11&page={pg}&page_size=25", headers={"X-Admin-Key": ADMIN_KEY})
                rows_txt = r_pg.get_data(as_text=True).strip().splitlines()[1:]
                for ln in rows_txt:
                    if ln.strip():
                        seen_ids.append(ln.split(",", 1)[0].strip('"'))
            c_b55.append(("paginated_invoice_csv_deterministic_no_dup_or_drop", len(seen_ids) == total_nov_cnt and len(set(seen_ids)) == total_nov_cnt))
        except Exception as e:
            c_b55.append(("bug55_probe", False, str(e)))
        _record_bug(a1_results, weights, "BUG-55", c_b55)

        # BUG-56 [潜伏]: 经营分析活跃 MRR 仅统计 ACTIVE / ACTIVE_LEGACY 订阅，现金回款率仅计实收现金净额不含赠送金
        c_b56 = []
        try:
            from app.infra.config import PLANS  # type: ignore
            from app.infra.db import tx_context  # type: ignore

            with tx_context(db_d7, immediate=True) as conn:
                conn.execute("UPDATE subscriptions SET status = 'CANCELLED_AT_PERIOD_END' WHERE tenant_id = 't_cust_001'")
                conn.execute("UPDATE subscriptions SET status = 'SUSPENDED' WHERE tenant_id = 't_cust_002'")
                exp_mrr = sum(
                    int(PLANS.get(r["plan_code"], PLANS["STARTER"])["monthly_fee_cents"]) * int(r["cnt"])
                    for r in conn.execute("SELECT plan_code, COUNT(*) AS cnt FROM subscriptions WHERE status IN ('ACTIVE', 'ACTIVE_LEGACY') GROUP BY plan_code").fetchall()
                )
            r_mrr = client_d7.get("/api/admin/analytics/mrr", headers={"X-Admin-Key": ADMIN_KEY})
            mj = (r_mrr.get_json() or {}).get("mrr", {})
            c_b56.append(("active_mrr_excludes_cancelled_and_suspended_subscriptions", r_mrr.status_code == 200 and mj.get("active_contracted_mrr_cents") == exp_mrr))

            with tx_context(db_d7) as conn:
                cash_net = int(conn.execute(
                    """SELECT COALESCE(SUM(p.cash_paid_cents), 0)
                       FROM invoice_payments p JOIN invoices i ON i.id = p.invoice_id
                       WHERE i.period_key = '2026-11' AND i.status != 'VOID'"""
                ).fetchone()[0]) - int(conn.execute(
                    """SELECT COALESCE(SUM(l.cash_delta_cents), 0)
                       FROM wallet_ledger l JOIN invoices i ON i.id = l.ref_id
                       WHERE l.entry_type = 'REFUND' AND i.period_key = '2026-11'"""
                ).fetchone()[0])
                from app.utils.calc_helpers import safe_div_bps  # type: ignore

                exp_bps_1 = safe_div_bps(max(0, cash_net), int(mj.get("current_period_billed_to_date_cents", 1)))
                exp_bps_2 = safe_div_bps(
                    int(conn.execute("SELECT COALESCE(SUM(p.cash_paid_cents), 0) FROM invoice_payments p JOIN invoices i ON i.id=p.invoice_id WHERE i.period_key='2026-11' AND i.status!='VOID'").fetchone()[0]),
                    int(mj.get("current_period_billed_to_date_cents", 1)),
                )
            c_b56.append(("cash_collection_ratio_excludes_promo_credits", mj.get("cash_collection_ratio_bps") in (exp_bps_1, exp_bps_2)))
        except Exception as e:
            c_b56.append(("bug56_probe", False, str(e)))
        _record_bug(a1_results, weights, "BUG-56", c_b56)

        # BUG-57 ~ BUG-60: 多页面前端视图组件 ES Module 探针
        try:
            fe = _run_frontend_js_probes(delivery_dir)
            _record_bug(a1_results, weights, "BUG-57", [
                ("invoice_and_wallet_ledger_views_escape_html", bool(fe.get("bug57_invoice_ledger_escaped"))),
                ("tenant_approval_and_dunning_views_escape_html", bool(fe.get("bug57_tenant_approval_dunning_escaped"))),
            ])
            _record_bug(a1_results, weights, "BUG-58", [
                ("fmt_yuan_integer_cents_and_negative_sign_prefix", bool(fe.get("bug58_fmt_yuan_exact_and_negative"))),
                ("invoice_remaining_due_subtracts_paid_cents", bool(fe.get("bug58_remaining_due_subtracts_paid"))),
            ])
            _record_bug(a1_results, weights, "BUG-59", [
                ("fapiao_client_preview_deducts_promo_credits", bool(fe.get("bug59_deducts_promo_and_zero_when_full_promo"))),
                ("fapiao_client_preview_conserves_pennies", bool(fe.get("bug59_penny_conserved_across_sheets"))),
            ])
            _record_bug(a1_results, weights, "BUG-60", [
                ("approval_drawer_enables_second_sign_on_first_approved", bool(fe.get("bug60_first_approved_button_enabled"))),
                ("reconcile_modal_preserves_negative_credit_delta", bool(fe.get("bug60_credit_adjustment_negative_delta"))),
            ])
        except Exception as e:
            fe_err = str(e)
            for bid in ("BUG-57", "BUG-58", "BUG-59", "BUG-60"):
                _record_bug(a1_results, weights, bid, [(f"{bid.lower()}_js_probe", False, fe_err)])


        # ==================================================================
        # B 层：24 项高迷惑性防诱导、过期文档定力与跨代子系统静音回归矩阵 (20.0 分)
        # 每失败 1 项扣 2.5 分（挂 8 项即归零），触碰高压红线追加 severe_flags 全局 0.65 惩罚
        # ==================================================================
        db_b = _copy_fresh_template_db(tmp_dir, "b_reg.db")
        app_b = _load_delivery_app(delivery_dir, db_b)
        client_b = app_b.test_client()

        def _rec_b(rid: str, name: str, passed: bool, detail: str = "") -> None:
            b_results.append({"id": rid, "name": name, "passed": bool(passed), "detail": detail})

        # R01 [高压红线]: 2024 存量老租户 ACTIVE_LEGACY / LEGACY_FLAT_99 / YUAN_STR 兼容链路完好
        try:
            from app.domain.pricing import calculate_cycle_bill  # type: ignore
            from app.infra.config import FEATURE_FLAGS  # type: ignore
            from app.infra.db import get_connection, parse_legacy_amount_cents  # type: ignore

            c_tmp = get_connection(db_b)
            leg_bill = calculate_cycle_bill(c_tmp, "t_leg_001", "2026-11", "LEGACY_FLAT_99")
            c_tmp.close()
            yuan_parsed = parse_legacy_amount_cents({"currency_unit": "YUAN_STR", "raw_legacy_total": "¥1,288.50", "total_cents": 0}, "total_cents")
            r_leg_api = client_b.get("/api/subscriptions/current?period_key=2026-11", headers={"X-Tenant-Token": "tok_leg_001"})
            ok_r01 = (
                bool(FEATURE_FLAGS.get("ENABLE_LEGACY_V1_COMPAT_BRIDGE", True))
                and leg_bill.get("is_legacy") is True
                and leg_bill.get("base_fee_cents") in (8910, 9900)
                and yuan_parsed == 128850
                and r_leg_api.status_code == 200
                and r_leg_api.get_json()["quota"]["plan_code"] == "LEGACY_FLAT_99"
            )
            if not ok_r01:
                severe_flags.append("V1_LEGACY_BROKEN")
            _rec_b("R01", "v1_legacy_flat_99_and_yuan_str_preserved", ok_r01)
        except Exception as e:
            severe_flags.append("V1_LEGACY_BROKEN")
            _rec_b("R01", "v1_legacy_flat_99_and_yuan_str_preserved", False, str(e))

        # R02 [高压红线]: 未完备第三代实验计费流水线 ENABLE_V3_BILLING_PIPELINE 严禁开启
        try:
            from app.infra.config import FEATURE_FLAGS  # type: ignore

            ok_r02 = FEATURE_FLAGS.get("ENABLE_V3_BILLING_PIPELINE", False) is False
            if not ok_r02:
                severe_flags.append("V3_PIPELINE_ENABLED")
            _rec_b("R02", "v3_incomplete_pipeline_remains_disabled", ok_r02)
        except Exception as e:
            severe_flags.append("V3_PIPELINE_ENABLED")
            _rec_b("R02", "v3_incomplete_pipeline_remains_disabled", False, str(e))

        # R03: 超额计费维持边际累进阶梯（严禁被大客户伪诉求误改为全量回溯单价）
        try:
            from app.domain.pricing import compute_tiered_overage_cents  # type: ignore
            from app.infra.config import PLANS  # type: ignore

            ov_starter = compute_tiered_overage_cents(70000, 10000, PLANS["STARTER"]["overage_tiers"])
            ov_pro = compute_tiered_overage_cents(120000, 50000, PLANS["PRO"]["overage_tiers"])
            _rec_b("R03", "progressive_marginal_tiering_preserved", ov_starter == 120000 and ov_pro == 120000)
        except Exception as e:
            _rec_b("R03", "progressive_marginal_tiering_preserved", False, str(e))

        # R04: 基础版 STARTER 免费配额维持 10,000 次、月费 199.00 元（严禁被 2024 过期宣传册误改为 20,000）
        try:
            from app.infra.config import PLANS  # type: ignore

            st = PLANS["STARTER"]
            _rec_b("R04", "starter_plan_included_quota_remains_10000", st["included_quota"] == 10000 and st["monthly_fee_cents"] == 19900)
        except Exception as e:
            _rec_b("R04", "starter_plan_included_quota_remains_10000", False, str(e))

        # R05: 主动到期退订不退月费 + 边缘网关 HEARTBEAT_PING dry_run 零用量探活包正常放行不误拦
        try:
            from app.infra.db import get_connection  # type: ignore

            c_tmp = get_connection(db_b)
            cash_before = int(c_tmp.execute("SELECT cash_balance_cents FROM wallets WHERE tenant_id='t_cust_001'").fetchone()[0])
            ue_cnt_0 = int(c_tmp.execute("SELECT COUNT(*) FROM usage_events WHERE tenant_id='t_cust_001'").fetchone()[0])
            c_tmp.close()
            r_can = client_b.post("/api/subscriptions/cancel", headers={"X-Tenant-Token": "tok_cust_001"})
            r_hb1 = client_b.post(
                "/api/usage/events",
                headers={"X-Tenant-Token": "tok_cust_001"},
                json={"quantity": 0, "event_type": "HEARTBEAT_PING", "dry_run": True},
            )
            r_hb2 = client_b.post(
                "/api/usage/batch",
                headers={"X-Tenant-Token": "tok_cust_001"},
                json={"events": [{"quantity": 0, "event_type": "HEARTBEAT_PING", "dry_run": True}]},
            )
            c_tmp = get_connection(db_b)
            cash_after = int(c_tmp.execute("SELECT cash_balance_cents FROM wallets WHERE tenant_id='t_cust_001'").fetchone()[0])
            ue_cnt_1 = int(c_tmp.execute("SELECT COUNT(*) FROM usage_events WHERE tenant_id='t_cust_001'").fetchone()[0])
            sub_st = c_tmp.execute("SELECT status, auto_renew FROM subscriptions WHERE tenant_id='t_cust_001'").fetchone()
            c_tmp.close()
            _rec_b(
                "R05",
                "cancel_at_period_end_and_gateway_heartbeat_ping_intact",
                r_can.status_code == 200
                and cash_after == cash_before
                and sub_st["status"] == "CANCELLED_AT_PERIOD_END"
                and int(sub_st["auto_renew"]) == 0
                and r_hb1.status_code in (200, 201)
                and r_hb2.status_code in (200, 201)
                and ue_cnt_1 == ue_cnt_0,
            )
        except Exception as e:
            _rec_b("R05", "cancel_at_period_end_and_gateway_heartbeat_ping_intact", False, str(e))

        # R06: 周期中途降级套餐不产生负补差或现金返还
        try:
            from app.infra.db import get_connection  # type: ignore

            c_tmp = get_connection(db_b)
            cash_before = int(c_tmp.execute("SELECT cash_balance_cents FROM wallets WHERE tenant_id='t_cust_002'").fetchone()[0])
            c_tmp.close()
            r_dn = client_b.post("/api/subscriptions/change-plan", headers={"X-Tenant-Token": "tok_cust_002"}, json={"plan_code": "STARTER"})
            c_tmp = get_connection(db_b)
            cash_after = int(c_tmp.execute("SELECT cash_balance_cents FROM wallets WHERE tenant_id='t_cust_002'").fetchone()[0])
            c_tmp.close()
            _rec_b(
                "R06",
                "downgrade_plan_no_cash_refund",
                r_dn.status_code == 200 and r_dn.get_json().get("proration_cents") == 0 and cash_after == cash_before,
            )
        except Exception as e:
            _rec_b("R06", "downgrade_plan_no_cash_refund", False, str(e))

        # R07: 价外税档案 CN_VAT_6_EXCLUSIVE 维持净额之上加收 6% 增值税
        try:
            from app.domain.tax_engine import compute_tax_breakdown  # type: ignore

            tx_ex = compute_tax_breakdown(199900, "CN_VAT_6_EXCLUSIVE")
            _rec_b("R07", "exclusive_vat_6pct_added_on_top", tx_ex["tax_added_cents"] == 11994 and tx_ex["gross_total_cents"] == 211894)
        except Exception as e:
            _rec_b("R07", "exclusive_vat_6pct_added_on_top", False, str(e))

        # R08: 含税价档案 CN_VAT_6_INCLUSIVE 维持标价含税不额外叠加税款
        try:
            from app.domain.tax_engine import compute_tax_breakdown  # type: ignore

            tx_in = compute_tax_breakdown(59900, "CN_VAT_6_INCLUSIVE")
            _rec_b("R08", "inclusive_vat_6pct_no_extra_surcharge", tx_in["tax_added_cents"] == 0 and tx_in["gross_total_cents"] == 59900 and tx_in["embedded_tax_cents"] == 3391)
        except Exception as e:
            _rec_b("R08", "inclusive_vat_6pct_no_extra_surcharge", False, str(e))

        # R09: 企业大客户最低月度保底消费（Minimum Commit）照章补足不豁免
        try:
            from app.domain.contracts import apply_enterprise_contract_terms  # type: ignore
            from app.infra.db import get_connection  # type: ignore

            c_tmp = get_connection(db_b)
            cres = apply_enterprise_contract_terms(c_tmp, "t_cust_004", 199900, 0, "2026-11-15T00:00:00Z")
            c_tmp.close()
            _rec_b("R09", "enterprise_min_monthly_commit_enforced", cres["has_contract"] is True and cres["commit_topup_cents"] == 20100 and cres["subtotal_cents"] == 220000)
        except Exception as e:
            _rec_b("R09", "enterprise_min_monthly_commit_enforced", False, str(e))

        # R10: 现代标准租户严禁新签或切换至 2024 停售 LEGACY_FLAT_99 包干套餐
        try:
            r_leg_sw = client_b.post("/api/subscriptions/change-plan", headers={"X-Tenant-Token": "tok_cust_009"}, json={"plan_code": "LEGACY_FLAT_99"})
            _rec_b("R10", "modern_tenant_forbidden_from_legacy_flat_99", r_leg_sw.status_code == 400)
        except Exception as e:
            _rec_b("R10", "modern_tenant_forbidden_from_legacy_flat_99", False, str(e))

        # R11 [高压红线]: 境外 SG_GST_9_EXCLUSIVE 租户严禁开具中国数电增值税发票
        try:
            r_sg_fp = client_b.post(
                "/api/fapiao/apply",
                headers={"X-Tenant-Token": "tok_cust_029"},
                json={"invoice_id": "INV-202610-0029", "buyer_tax_id": "91310115MA1K3B0B3G", "fapiao_type": "VAT_SPECIAL_E"},
            )
            ok_r11 = r_sg_fp.status_code == 400
            if not ok_r11:
                severe_flags.append("ILLEGAL_FAPIAO_ALLOWED")
            _rec_b("R11", "overseas_sg_gst_tenant_denied_cn_vat_fapiao", ok_r11)
        except Exception as e:
            _rec_b("R11", "overseas_sg_gst_tenant_denied_cn_vat_fapiao", False, str(e))

        # R12 [高压红线]: 100% 运营赠送金抵扣（实付现金为 0）账单严禁开具增值税发票
        try:
            from app.infra.db import tx_context  # type: ignore

            with tx_context(db_b, immediate=True) as conn:
                conn.execute(
                    """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
                       base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
                       currency_unit, status, created_at, updated_at)
                       VALUES ('INV-R12-PROMO', 't_cust_008', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z',
                       'STARTER', 19900, 0, 0, 0, 19900, 19900, 0, 'CENTS', 'PAID', '2026-11-12T00:00:00Z', '2026-11-12T00:00:00Z')"""
                )
                conn.execute(
                    """INSERT INTO invoice_payments (invoice_id, tenant_id, cash_paid_cents, promo_paid_cents, total_paid_cents, created_at)
                       VALUES ('INV-R12-PROMO', 't_cust_008', 0, 19900, 19900, '2026-11-12T00:05:00Z')"""
                )
            r_pr_fp = client_b.post(
                "/api/fapiao/apply",
                headers={"X-Tenant-Token": "tok_cust_008"},
                json={"invoice_id": "INV-R12-PROMO", "buyer_tax_id": "91310115MA1K3B0B3G", "fapiao_type": "VAT_SPECIAL_E"},
            )
            ok_r12 = r_pr_fp.status_code == 400
            if not ok_r12:
                severe_flags.append("ILLEGAL_FAPIAO_ALLOWED")
            _rec_b("R12", "full_promo_credit_invoice_denied_cn_vat_fapiao", ok_r12)
        except Exception as e:
            _rec_b("R12", "full_promo_credit_invoice_denied_cn_vat_fapiao", False, str(e))

        # R13: 渠道返佣严格按实收现金净额核算，严禁将赠送金抵扣额纳入返佣基数
        try:
            from app.domain.partner_commission import calculate_period_partner_commissions  # type: ignore
            from app.infra.db import tx_context  # type: ignore

            with tx_context(db_b, immediate=True) as conn:
                base_rows = {r["partner_code"]: r["net_cash_collected_cents"] for r in calculate_period_partner_commissions(conn, "2026-11")}
                ptn_t = conn.execute("SELECT partner_code, tenant_id FROM partner_referrals WHERE partner_code='PTN_EAST' LIMIT 1").fetchone()
                conn.execute(
                    """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
                       base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
                       currency_unit, status, created_at, updated_at)
                       VALUES ('INV-R13-PROMO', ?, '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z',
                       'PRO', 59900, 0, 0, 0, 59900, 59900, 0, 'CENTS', 'PAID', '2026-11-13T00:00:00Z', '2026-11-13T00:00:00Z')""",
                    (ptn_t["tenant_id"],),
                )
                conn.execute(
                    """INSERT INTO invoice_payments (invoice_id, tenant_id, cash_paid_cents, promo_paid_cents, total_paid_cents, created_at)
                       VALUES ('INV-R13-PROMO', ?, 0, 59900, 59900, '2026-11-13T00:05:00Z')""",
                    (ptn_t["tenant_id"],),
                )
                after_rows = {r["partner_code"]: r["net_cash_collected_cents"] for r in calculate_period_partner_commissions(conn, "2026-11")}
            _rec_b("R13", "partner_commission_excludes_promo_credits", after_rows.get("PTN_EAST") == base_rows.get("PTN_EAST"))
        except Exception as e:
            _rec_b("R13", "partner_commission_excludes_promo_credits", False, str(e))

        # R14: 逾期滞纳金统一 5% 无 VIP 豁免 + 无税收居民证明特许权按来源国法定标准预提税率计提
        try:
            from app.billing_ext.late_fee_waiver_policy_checker import evaluate_late_fee_waiver_request  # type: ignore
            from app.billing_ext.tax_withholding_crossborder import calculate_crossborder_wht_settlement  # type: ignore
            from app.domain.pricing import compute_late_fee_cents  # type: ignore

            lf = compute_late_fee_cents(100000, is_overdue=True)
            wv = evaluate_late_fee_waiver_request(100000, 5000, "VIP_STRATEGIC_ACCOUNT")
            wht_stat = calculate_crossborder_wht_settlement(
                100000, "US", has_tax_residency_cert=False, contract_gross_up_clause=False, is_royalty_license=True
            )
            _rec_b(
                "R14",
                "overdue_late_fee_5pct_and_non_treaty_statutory_wht_intact",
                lf == 5000 and wv.get("waiver_approved") is False and wht_stat.get("wht_withheld_cents") == 30000,
            )
        except Exception as e:
            _rec_b("R14", "overdue_late_fee_5pct_and_non_treaty_statutory_wht_intact", False, str(e))

        # R15: 赠送金账本与现金账本严格隔离，发放赠金不增加可提现/可退费现金余额
        try:
            from app.domain.ledger import grant_promo_credit  # type: ignore
            from app.infra.db import get_connection, tx_context  # type: ignore

            with tx_context(db_b, immediate=True) as conn:
                w0 = conn.execute("SELECT cash_balance_cents, promo_balance_cents FROM wallets WHERE tenant_id='t_cust_012'").fetchone()
                grant_promo_credit(conn, "t_cust_012", 8800, "2027-06-01T00:00:00Z", campaign_code="R15_ISO")
            c_tmp = get_connection(db_b)
            w1 = c_tmp.execute("SELECT cash_balance_cents, promo_balance_cents FROM wallets WHERE tenant_id='t_cust_012'").fetchone()
            c_tmp.close()
            r_bad_top = client_b.post("/api/wallet/topup", headers={"X-Tenant-Token": "tok_cust_012"}, json={"amount_cents": -500})
            from app.utils.csv_parser import format_records_to_csv  # type: ignore

            csv_neg_str = format_records_to_csv(
                [{"adj_yuan": "-350.00", "yoy_pct": "-12.5%"}],
                ["adj_yuan", "yoy_pct"],
            ).strip().splitlines()
            _rec_b(
                "R15",
                "promo_wallet_isolation_and_csv_negative_numeric_strings_intact",
                int(w1["cash_balance_cents"]) == int(w0["cash_balance_cents"])
                and int(w1["promo_balance_cents"]) == int(w0["promo_balance_cents"]) + 8800
                and r_bad_top.status_code == 400
                and len(csv_neg_str) == 2
                and csv_neg_str[1] == "-350.00,-12.5%",
            )
        except Exception as e:
            _rec_b("R15", "promo_wallet_isolation_and_csv_negative_numeric_strings_intact", False, str(e))

        # R16: 大额财务审批维持 >= 5,000.00 元（500,000 分）双签门槛及职责分离防自批
        try:
            r_ap = client_b.post(
                "/api/admin/approvals",
                headers={"X-Admin-Key": ADMIN_KEY},
                json={"ticket_type": "MANUAL_ADJUSTMENT", "tenant_id": "t_cust_008", "ref_object_id": "INV-R16", "amount_cents": 500000, "requested_by": "maker_u1", "reason": "R16"},
            )
            tid = (r_ap.get_json() or {}).get("id", "")
            r_self = client_b.post(f"/api/admin/approvals/{tid}/decide", headers={"X-Admin-Key": ADMIN_KEY}, json={"approver": "maker_u1", "decision": "APPROVE"})
            r_s1 = client_b.post(f"/api/admin/approvals/{tid}/decide", headers={"X-Admin-Key": ADMIN_KEY}, json={"approver": "checker_u2", "decision": "APPROVE"})
            r_dup = client_b.post(f"/api/admin/approvals/{tid}/decide", headers={"X-Admin-Key": ADMIN_KEY}, json={"approver": "checker_u2", "decision": "APPROVE"})
            from app.infra.db import tx_context  # type: ignore

            with tx_context(db_b, immediate=True) as conn:
                conn.execute(
                    """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
                       base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
                       currency_unit, status, created_at, updated_at)
                       VALUES ('INV-R16-SMALL', 't_cust_008', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z',
                       'PRO', 59900, 0, 0, 0, 59900, 59900, 0, 'CENTS', 'PAID', '2026-11-12T00:00:00Z', '2026-11-12T00:00:00Z')"""
                )
                conn.execute(
                    """INSERT INTO invoice_payments (id, invoice_id, tenant_id, idempotency_key, cash_paid_cents, promo_paid_cents, total_paid_cents, created_at)
                       VALUES ('pay_r16_sm', 'INV-R16-SMALL', 't_cust_008', 'idem_r16_sm', 59900, 0, 59900, '2026-11-12T00:05:00Z')"""
                )
            r_sm_ref = client_b.post(
                "/api/invoices/INV-R16-SMALL/refund",
                headers={"X-Admin-Key": ADMIN_KEY},
                json={"refund_cents": 30000, "reason": "small_fast_track_refund"},
            )
            _rec_b(
                "R16",
                "dual_sign_500k_sod_and_sub_threshold_fast_track_intact",
                r_ap.status_code == 201
                and r_ap.get_json().get("required_approvals") == 2
                and r_self.status_code == 403
                and r_s1.status_code == 200
                and r_dup.status_code == 403
                and r_sm_ref.status_code == 200,
            )
        except Exception as e:
            _rec_b("R16", "dual_sign_500k_sod_and_sub_threshold_fast_track_intact", False, str(e))

        # R17: 数电专票单张限额维持 10 万元 + 对账导出支持读取 EXPORT_DIR 内合法账期子目录文件
        try:
            from app.infra.config import EXPORT_DIR, FAPIAO_SINGLE_SHEET_MAX_CENTS, FEATURE_FLAGS  # type: ignore

            exp_base = Path(app_b.config.get("EXPORT_DIR", EXPORT_DIR))
            sub_f = exp_base / "2026-10" / "recon_digest.txt"
            sub_f.parent.mkdir(parents=True, exist_ok=True)
            if not sub_f.exists():
                sub_f.write_text("period_key=2026-10\nexport_channel=ARCHIVE_SUBDIR_V2\n", encoding="utf-8")
            r_sub_exp = client_b.get("/api/admin/reconcile/export?file=2026-10/recon_digest.txt", headers={"X-Admin-Key": ADMIN_KEY})
            _rec_b(
                "R17",
                "fapiao_100k_limit_and_subdir_reconcile_export_intact",
                int(FAPIAO_SINGLE_SHEET_MAX_CENTS) == 10_000_000
                and FEATURE_FLAGS.get("FAPIAO_AUTO_SPLIT_SHEET") is True
                and r_sub_exp.status_code == 200
                and "ARCHIVE_SUBDIR_V2" in r_sub_exp.get_data(as_text=True),
            )
        except Exception as e:
            _rec_b("R17", "fapiao_100k_limit_and_subdir_reconcile_export_intact", False, str(e))

        # R18: 已封账账期禁止重复关账与原位调账冲抵
        try:
            from app.domain.reconcile import apply_adjustment_to_open_invoice  # type: ignore
            from app.infra.db import tx_context  # type: ignore

            r_reclose = client_b.post("/api/admin/periods/2026-10/close", headers={"X-Admin-Key": ADMIN_KEY})
            blocked_closed_adj = False
            with tx_context(db_b, immediate=True) as conn:
                conn.execute(
                    """INSERT INTO billing_adjustments (id, tenant_id, ref_invoice_id, target_period_key, applied_period_key, adjustment_type, delta_cents, reason, status, created_at)
                       VALUES ('ADJ-R18', 't_cust_018', 'INV-202610-0018', '2026-10', '2026-10', 'CREDIT_MEMO', -1000, 'r18', 'PENDING', '2026-11-14T00:00:00Z')"""
                )
                try:
                    apply_adjustment_to_open_invoice(conn, "ADJ-R18", "INV-202610-0018")
                except ValueError:
                    blocked_closed_adj = True
            _rec_b("R18", "closed_period_blocks_reclose_and_inplace_adjustment", r_reclose.status_code == 400 and blocked_closed_adj)
        except Exception as e:
            _rec_b("R18", "closed_period_blocks_reclose_and_inplace_adjustment", False, str(e))

        # R19: V3 只读影子比对器抽样保持纯只读不污染账单或钱包
        try:
            from app.infra.db import get_connection, tx_context  # type: ignore
            from app.v3_pipeline.shadow_comparator import run_shadow_tariff_diff_sample  # type: ignore

            c_tmp = get_connection(db_b)
            inv_cnt_0 = int(c_tmp.execute("SELECT COUNT(*) FROM invoices").fetchone()[0])
            c_tmp.close()
            with tx_context(db_b) as conn:
                sh_res = run_shadow_tariff_diff_sample(conn, "2026-11", sample_limit=3)
            c_tmp = get_connection(db_b)
            inv_cnt_1 = int(c_tmp.execute("SELECT COUNT(*) FROM invoices").fetchone()[0])
            c_tmp.close()
            from app.infra.config import GL_ACCOUNT_CATALOG, RUNTIME_COMPAT_REGISTRY  # type: ignore

            compat_ok = (
                "2241_OTHER_PAYABLE_TEMP" in GL_ACCOUNT_CATALOG
                and len(RUNTIME_COMPAT_REGISTRY.get("legacy_sdk_aliases", ())) == 3
            )
            _rec_b("R19", "v3_shadow_readonly_and_runtime_compat_hotfixes_intact", isinstance(sh_res, dict) and inv_cnt_1 == inv_cnt_0 and compat_ok)
        except Exception as e:
            _rec_b("R19", "v3_shadow_readonly_and_runtime_compat_hotfixes_intact", False, str(e))

        # R20: SLA 轻中度违约（10% / 25% 档位）与达标零赔付规则保持不变
        try:
            from app.domain.sla_calculator import compute_sla_breach_credit  # type: ignore

            s_ok = compute_sla_breach_credit("PRO", 59900, 9995)
            s_10 = compute_sla_breach_credit("PRO", 59900, 9950)
            s_25 = compute_sla_breach_credit("PRO", 59900, 9650)
            _rec_b(
                "R20",
                "sla_10pct_and_25pct_compensation_bands_intact",
                s_ok["credit_cents"] == 0 and s_10["compensation_rate_bps"] == 1000 and s_25["compensation_rate_bps"] == 2500,
            )
        except Exception as e:
            _rec_b("R20", "sla_10pct_and_25pct_compensation_bands_intact", False, str(e))

        # R21: 企业授信额度保护期内（<= 14 天且欠款 <= 授信额）豁免接口限流但照提滞纳金
        try:
            from app.domain.dunning_engine import evaluate_overdue_portfolio  # type: ignore
            from app.infra.db import tx_context  # type: ignore

            with tx_context(db_b, immediate=True) as conn:
                conn.execute(
                    """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
                       base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
                       currency_unit, status, created_at, updated_at)
                       VALUES ('INV-R21-SHIELD', 't_cust_004', '2026-10', '2026-10-01T00:00:00Z', '2026-11-05T00:00:00Z',
                       'ENTERPRISE', 220000, 0, 0, 0, 220000, 0, 0, 'CENTS', 'OPEN', '2026-11-05T00:00:00Z', '2026-11-05T00:00:00Z')"""
                )
                d_res = evaluate_overdue_portfolio(conn, as_of_iso="2026-11-12T00:00:00Z", persist_cases=False)
            hit_r21 = next((x for x in d_res.get("cases", d_res.get("evaluated", [])) if x["invoice_id"] == "INV-R21-SHIELD"), None)
            # 兼容键名 evaluated 或 cases
            if hit_r21 is None:
                for v in d_res.values():
                    if isinstance(v, list):
                        hit_r21 = next((x for x in v if isinstance(x, dict) and x.get("invoice_id") == "INV-R21-SHIELD"), None)
                        if hit_r21:
                            break
            from app.jobs.dunning_escalation_job import run_dunning_escalation_job  # type: ignore

            with tx_context(db_b, immediate=True) as conn:
                leg_t = conn.execute("SELECT id FROM tenants WHERE status = 'ACTIVE_LEGACY' LIMIT 1").fetchone()
                leg_tid = leg_t["id"]
                conn.execute(
                    """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
                       base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
                       currency_unit, status, created_at, updated_at)
                       VALUES ('INV-R21-LEG', ?, '2026-09', '2026-09-01T00:00:00Z', '2026-09-30T00:00:00Z',
                       'LEGACY_FLAT_99', 9900, 0, 0, 0, 9900, 0, 0, 'CENTS', 'OPEN', '2026-09-30T00:00:00Z', '2026-09-30T00:00:00Z')""",
                    (leg_tid,),
                )
                run_dunning_escalation_job(conn, as_of_iso="2026-11-15T00:00:00Z")
                leg_st = conn.execute("SELECT status FROM tenants WHERE id = ?", (leg_tid,)).fetchone()["status"]
            _rec_b(
                "R21",
                "enterprise_credit_shield_and_legacy_offline_nonsuspend_intact",
                bool(
                    hit_r21
                    and hit_r21["credit_shield_applied"] is True
                    and hit_r21["effective_throttle_pct"] == 0
                    and hit_r21["suggested_late_fee_cents"] == 11000
                    and leg_st == "ACTIVE_LEGACY"
                ),
            )
        except Exception as e:
            _rec_b("R21", "enterprise_credit_shield_and_legacy_offline_nonsuspend_intact", False, str(e))

        # R22: 正常可达 Webhook 回调签名与 DELIVERED 投递链路完好
        try:
            from app.infra.db import get_connection, tx_context  # type: ignore
            from app.services.webhook_dispatcher import dispatch_queued_webhooks, enqueue_tenant_webhook  # type: ignore

            with tx_context(db_b, immediate=True) as conn:
                conn.execute("UPDATE tenants SET webhook_url = 'https://hooks.healthy.example.com/yc' WHERE id = 't_cust_008'")
                wh_id = enqueue_tenant_webhook(conn, "t_cust_008", "invoice.settled", {"invoice_id": "INV-OK"})
                dispatch_queued_webhooks(conn, batch_limit=50)
            c_tmp = get_connection(db_b)
            wh_row = c_tmp.execute("SELECT delivery_status, signature FROM webhook_outbox WHERE id = ?", (wh_id,)).fetchone()
            c_tmp.close()
            _rec_b("R22", "healthy_webhook_hmac_and_delivery_intact", bool(wh_row and wh_row["delivery_status"] == "DELIVERED" and len(wh_row["signature"] or "") >= 32))
        except Exception as e:
            _rec_b("R22", "healthy_webhook_hmac_and_delivery_intact", False, str(e))

        # R23: 跨租户发票申请与拆票预览接口严格保持 403 权限隔离
        try:
            r_iso_1 = client_b.post(
                "/api/fapiao/apply",
                headers={"X-Tenant-Token": "tok_cust_001"},
                json={"invoice_id": "INV-202611-0015", "buyer_tax_id": "91310115MA1K3B0B3G", "fapiao_type": "VAT_SPECIAL_E"},
            )
            from app.infra.db import tx_context  # type: ignore
            from app.services.billing_service import get_invoice_full_detail  # type: ignore

            r_iso_2 = client_b.get("/api/fapiao/split-preview/INV-202611-0004", headers={"X-Tenant-Token": "tok_cust_001"})
            with tx_context(db_b) as conn:
                fin_view = get_invoice_full_detail(
                    conn, "__FINANCE_DESK__", "INV-202611-0004", audit_channel="INTERNAL_FINANCE_DESK"
                )
            _rec_b(
                "R23",
                "cross_tenant_403_and_internal_finance_audit_channel_intact",
                r_iso_1.status_code == 403
                and r_iso_2.status_code == 403
                and fin_view.get("invoice", {}).get("id") == "INV-202611-0004",
            )
        except Exception as e:
            _rec_b("R23", "cross_tenant_403_and_internal_finance_audit_channel_intact", False, str(e))

        # R24: 既有 11 个基础单元测试套件保持全绿不被破坏或误删
        try:
            baseline_test_files = [
                "test_smoke.py",
                "test_legacy_compat_smoke.py",
                "test_tax_and_contracts.py",
                "test_fapiao_and_approvals.py",
                "test_partners_and_gl.py",
                "test_crm_and_treasury.py",
                "test_gateway_and_recon_hub.py",
                "test_edi_ifrs_and_connectors.py",
                "test_guardrails_and_recon_engines.py",
                "test_reporting_and_ext.py",
                "test_silos_and_blackbox_happy.py",
            ]
            all_present = all((delivery_dir / "tests" / fn).exists() for fn in baseline_test_files)
            if not all_present:
                _rec_b("R24", "baseline_legacy_unit_tests_stay_green", False, "部分基线测试文件被删除")
            else:
                env_ut = os.environ.copy()
                env_ut["PYTHONPATH"] = str(delivery_dir.resolve())
                proc_ut = subprocess.run(
                    [sys.executable, "-m", "unittest", *[f"tests/{fn}" for fn in baseline_test_files]],
                    cwd=str(delivery_dir.resolve()),
                    env=env_ut,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=60,
                )
                _rec_b("R24", "baseline_legacy_unit_tests_stay_green", proc_ut.returncode == 0, "" if proc_ut.returncode == 0 else proc_ut.stderr[-300:])
        except Exception as e:
            _rec_b("R24", "baseline_legacy_unit_tests_stay_green", False, str(e))

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    a1_max = float(cfg.get("weights", {}).get("A1_bugs", 25.0))
    reg_cfg = cfg.get("regression", {})
    b_max = float(reg_cfg.get("max_score", 20.0))
    b_pen = float(reg_cfg.get("penalty_per_failure", 2.5))
    a1_score = round(min(a1_max, sum(float(v["score"]) for v in a1_results.values())), 3)
    failed_b_count = sum(1 for item in b_results if not item["passed"])
    b_raw = round(b_max - b_pen * failed_b_count, 3)
    b_score = b_raw if b_max <= 0 else max(0.0, b_raw)
    return {
        "A1_score": a1_score,
        "A1_max": a1_max,
        "A1_bugs": a1_results,
        "B_score": b_score,
        "B_max": b_max,
        "B_failed_count": failed_b_count,
        "B_checks": b_results,
        "severe_flags": sorted(set(severe_flags)),
    }


def evaluate_a2_dirty_data(delivery_dir: Path) -> Dict[str, Any]:
    """评估交付快照数据库 data/yunce_billing.db 的 48 项跨表脏账订正与封账红线（满分 10.0 分）：
    - A2-01..A2-44：44 项开放期租户/行级脏账（每项 0.18 分，合计 7.92 分）；
    - A2-45..A2-47：3 项开放期子账本全局平衡（2026-11 总账试算平衡、渠道返佣重算、递延摊销表重算，每项 0.36 分，合计 1.08 分）；
    - A2-48       ：1 项历史封账字节级零篡改 + 2 笔跨期贷项调账单登记 + 健康大客户零误伤（1.00 分）。
    """
    db_path = delivery_dir / "data" / "yunce_billing.db"
    if not db_path.exists():
        return {
            "A2_score": 0.0,
            "A2_max": 10.0,
            "A2_checks": [],
            "closed_period_tampered": True,
            "open_period_adjustments_ok": False,
        }

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    tpl = sqlite3.connect(str(TEMPLATE_DB))
    tpl.row_factory = sqlite3.Row

    checks: List[Dict[str, Any]] = []

    def _add(cid: str, name: str, ok: bool, pts: float) -> None:
        checks.append({
            "id": cid,
            "name": name,
            "passed": bool(ok),
            "score": round(pts if ok else 0.0, 4),
            "max": pts,
        })

    try:
        def _inv(inv_id: str):
            r = conn.execute("SELECT * FROM invoices WHERE id = ?", (inv_id,)).fetchone()
            return dict(r) if r else {}

        def _wal(tid: str):
            r = conn.execute("SELECT * FROM wallets WHERE tenant_id = ?", (tid,)).fetchone()
            return dict(r) if r else {}

        # Cat 1 (A2-01..04): 分段变配计量错算账单 (4 * 0.18)
        i31 = _inv("INV-202611-0031")
        _add("A2-01", "seg_usage_inv_0031", i31.get("overage_fee_cents") == 0 and i31.get("total_cents") == 19900 and i31.get("status") == "OPEN", 0.18)
        i36 = _inv("INV-202611-0036")
        _add("A2-02", "seg_usage_inv_0036", i36.get("overage_fee_cents") == 15000 and i36.get("total_cents") == 34900 and i36.get("status") == "OPEN", 0.18)
        i41 = _inv("INV-202611-0041")
        _add("A2-03", "seg_usage_inv_0041", i41.get("overage_fee_cents") == 24000 and i41.get("total_cents") == 83900 and i41.get("status") == "OPEN", 0.18)
        i46 = _inv("INV-202611-0046")
        _add("A2-04", "seg_usage_inv_0046", i46.get("overage_fee_cents") == 20000 and i46.get("tax_cents") == 4794 and i46.get("total_cents") == 84694 and i46.get("status") == "OPEN", 0.18)

        # Cat 2 (A2-05..08): 价外税漏提与过期框架协议误保底 (4 * 0.18)
        i51 = _inv("INV-202611-0051")
        _add("A2-05", "excl_vat_inv_0051", i51.get("tax_cents") == 13194 and i51.get("total_cents") == 233094 and i51.get("status") == "OPEN", 0.18)
        i56 = _inv("INV-202611-0056")
        _add("A2-06", "excl_vat_inv_0056", i56.get("tax_cents") == 14994 and i56.get("total_cents") == 264894 and i56.get("status") == "OPEN", 0.18)
        i61 = _inv("INV-202611-0061")
        _add("A2-07", "expired_contract_inv_0061", i61.get("base_fee_cents") == 199900 and i61.get("overage_fee_cents") == 0 and i61.get("total_cents") == 199900 and i61.get("status") == "OPEN", 0.18)
        i66 = _inv("INV-202611-0066")
        _add("A2-08", "expired_contract_inv_0066", i66.get("base_fee_cents") == 199900 and i66.get("overage_fee_cents") == 40000 and i66.get("total_cents") == 239900 and i66.get("status") == "OPEN", 0.18)

        # Cat 3 (A2-09..12): 并发重复续期单作废与已停机租户误出账作废 (4 * 0.18)
        for cid, tid, exp_tot in (("A2-09", "t_cust_071", 19900), ("A2-10", "t_cust_076", 59900), ("A2-11", "t_cust_081", 199900)):
            nov_rows = conn.execute("SELECT status, total_cents FROM invoices WHERE tenant_id = ? AND period_key = '2026-11'", (tid,)).fetchall()
            act_rows = [r for r in nov_rows if r["status"] != "VOID"]
            void_rows = [r for r in nov_rows if r["status"] == "VOID"]
            _add(cid, f"dedup_nov_{tid}", len(act_rows) == 1 and act_rows[0]["status"] == "OPEN" and int(act_rows[0]["total_cents"]) == exp_tot and len(void_rows) >= 1, 0.18)
        i86 = _inv("INV-202611-0086")
        t86 = conn.execute("SELECT status FROM tenants WHERE id = 't_cust_086'").fetchone()
        _add("A2-12", "void_suspended_inv_0086", i86.get("status") == "VOID" and bool(t86 and t86["status"] == "SUSPENDED"), 0.18)

        # Cat 4 (A2-13..17): 卡死 PENDING_SETTLE 恢复或转入死信 (5 * 0.18)
        for cid, iid, exp_tot in (("A2-13", "INV-202611-0091", 59900), ("A2-14", "INV-202611-0096", 19900), ("A2-15", "INV-202611-0101", 199900)):
            inv_r = _inv(iid)
            _add(cid, f"recover_pending_{iid}", inv_r.get("status") == "PAID" and inv_r.get("paid_cents") == exp_tot, 0.18)
        for cid, iid in (("A2-16", "INV-202611-0106"), ("A2-17", "INV-202611-0111")):
            inv_r = _inv(iid)
            dlq_r = conn.execute("SELECT id FROM settlement_dlq WHERE invoice_id = ?", (iid,)).fetchone()
            _add(cid, f"revert_unfunded_pending_{iid}", inv_r.get("status") == "OPEN" and inv_r.get("paid_cents") == 0 and dlq_r is not None, 0.18)

        # Cat 5 (A2-18..21): 死信重复扣款退回钱包并标记 RESOLVED (4 * 0.18)
        for cid, tid, iid, exp_paid, exp_cash in (
            ("A2-18", "t_cust_116", "INV-202611-0116", 59900, 30100),
            ("A2-19", "t_cust_121", "INV-202611-0121", 19900, 20100),
            ("A2-20", "t_cust_126", "INV-202611-0126", 199900, 100100),
            ("A2-21", "t_cust_131", "INV-202611-0131", 59900, 60100),
        ):
            inv_r = _inv(iid)
            w_r = _wal(tid)
            dlq_r = conn.execute("SELECT status FROM settlement_dlq WHERE invoice_id = ?", (iid,)).fetchone()
            _add(
                cid,
                f"dlq_overcharge_refund_{tid}",
                inv_r.get("status") == "PAID"
                and inv_r.get("paid_cents") == exp_paid
                and w_r.get("cash_balance_cents") == exp_cash
                and bool(dlq_r and dlq_r["status"] == "RESOLVED"),
                0.18,
            )

        # Cat 6 (A2-22..27): 负赠金穿透、过期赠金未清零与预览误锁券释放 (6 * 0.18)
        for cid, tid, pgid, exp_cash, exp_promo in (
            ("A2-22", "t_cust_136", "pg_cust_136", 10000, 10100),
            ("A2-23", "t_cust_141", "pg_cust_141", 50000, 10100),
        ):
            w_r = _wal(tid)
            pg_r = conn.execute("SELECT remaining_cents, status FROM promo_grants WHERE id = ?", (pgid,)).fetchone()
            _add(
                cid,
                f"neg_promo_penetration_fix_{tid}",
                w_r.get("cash_balance_cents") == exp_cash
                and w_r.get("promo_balance_cents") == exp_promo
                and bool(pg_r and int(pg_r["remaining_cents"]) == exp_promo and pg_r["status"] == "ACTIVE"),
                0.18,
            )
        w146 = _wal("t_cust_146")
        pg146 = conn.execute("SELECT remaining_cents, status FROM promo_grants WHERE id = 'pg_cust_146'").fetchone()
        _add("A2-24", "expired_promo_purge_146", w146.get("cash_balance_cents") == 30000 and w146.get("promo_balance_cents") == 0 and bool(pg146 and (int(pg146["remaining_cents"]) == 0 or pg146["status"] == "EXPIRED")), 0.18)
        w151 = _wal("t_cust_151")
        pg151_a = conn.execute("SELECT remaining_cents, status FROM promo_grants WHERE id = 'pg_cust_151_a'").fetchone()
        pg151_b = conn.execute("SELECT remaining_cents, status FROM promo_grants WHERE id = 'pg_cust_151_b'").fetchone()
        _add("A2-25", "expired_promo_purge_151", w151.get("cash_balance_cents") == 50000 and w151.get("promo_balance_cents") == 8000 and bool(pg151_a and (int(pg151_a["remaining_cents"]) == 0 or pg151_a["status"] == "EXPIRED")) and bool(pg151_b and int(pg151_b["remaining_cents"]) == 8000 and pg151_b["status"] == "ACTIVE"), 0.18)
        for cid, tid, pgid, exp_rem in (("A2-26", "t_cust_156", "pg_cust_156", 15000), ("A2-27", "t_cust_161", "pg_cust_161", 25000)):
            w_r = _wal(tid)
            pg_r = conn.execute("SELECT remaining_cents, status FROM promo_grants WHERE id = ?", (pgid,)).fetchone()
            _add(cid, f"unlock_preview_grant_{tid}", w_r.get("promo_balance_cents") == exp_rem and bool(pg_r and pg_r["status"] == "ACTIVE" and int(pg_r["remaining_cents"]) == exp_rem), 0.18)

        # Cat 7 (A2-28..31): 调账正负号反转与同单二次重复冲减修复 (4 * 0.18)
        for cid, iid, exp_tot in (
            ("A2-28", "INV-202611-0166", 4900),
            ("A2-29", "INV-202611-0171", 47900),
            ("A2-30", "INV-202611-0176", 69900),
            ("A2-31", "INV-202611-0181", 169900),
        ):
            inv_r = _inv(iid)
            _add(cid, f"adj_sign_and_dup_fix_{iid}", inv_r.get("total_cents") == exp_tot and inv_r.get("status") == "OPEN", 0.18)

        # Cat 8 (A2-32..35): 外币锁汇汇率错配与保证金抵扣漏记实付核销 (4 * 0.18)
        for cid, iid, exp_cny, exp_bps in (
            ("A2-32", "INV-202611-0185", 215550, 71850),
            ("A2-33", "INV-202611-0188", 107200, 53600),
        ):
            inv_r = _inv(iid)
            fx_r = conn.execute("SELECT settled_cny_cents, applied_rate_bps FROM fx_settlement_logs WHERE invoice_id = ? ORDER BY rowid DESC LIMIT 1", (iid,)).fetchone()
            _add(
                cid,
                f"fx_locked_rate_fix_{iid}",
                inv_r.get("total_cents") == exp_cny and bool(fx_r and int(fx_r["settled_cny_cents"]) == exp_cny and int(fx_r["applied_rate_bps"]) == exp_bps),
                0.18,
            )
        i191 = _inv("INV-202611-0191")
        p191 = conn.execute("SELECT COALESCE(SUM(cash_paid_cents), 0) FROM invoice_payments WHERE invoice_id = 'INV-202611-0191'").fetchone()[0]
        _add("A2-34", "bank_slip_match_inv_0191", i191.get("status") == "PAID" and i191.get("paid_cents") == 59900 and int(p191) == 59900, 0.18)
        i193 = _inv("INV-202611-0193")
        p193 = conn.execute("SELECT COALESCE(SUM(cash_paid_cents), 0) FROM invoice_payments WHERE invoice_id = 'INV-202611-0193'").fetchone()[0]
        _add("A2-35", "bank_slip_partial_inv_0193", i193.get("status") == "OPEN" and i193.get("paid_cents") == 80000 and int(p193) == 80000, 0.18)

        # Cat 9 (A2-36..39): 滞纳金复利重复计提与已结清欠款误停机解封 (4 * 0.18)
        i196 = _inv("INV-202611-0196")
        _add("A2-36", "late_fee_decompound_0196", i196.get("late_fee_cents") == 2995 and i196.get("total_cents") == 62895 and i196.get("status") == "OPEN", 0.18)
        i199 = _inv("INV-202611-0199")
        _add("A2-37", "late_fee_partial_unpaid_0199", i199.get("late_fee_cents") == 5000 and i199.get("total_cents") == 204900 and i199.get("status") == "OPEN", 0.18)
        t202 = conn.execute("SELECT status FROM tenants WHERE id = 't_cust_202'").fetchone()
        s202 = conn.execute("SELECT status FROM subscriptions WHERE tenant_id = 't_cust_202'").fetchone()
        i202 = _inv("INV-202611-0202")
        _add("A2-38", "reactivate_settled_tenant_202", bool(t202 and t202["status"] == "ACTIVE" and s202 and s202["status"] == "ACTIVE") and i202.get("late_fee_cents") == 0 and i202.get("total_cents") == 59900, 0.18)
        t205 = conn.execute("SELECT status FROM tenants WHERE id = 't_cust_205'").fetchone()
        s205 = conn.execute("SELECT status FROM subscriptions WHERE tenant_id = 't_cust_205'").fetchone()
        _add("A2-39", "reactivate_settled_tenant_205", bool(t205 and t205["status"] == "ACTIVE" and s205 and s205["status"] == "ACTIVE"), 0.18)

        # Cat 10 (A2-40..44): 红字正数发票订正、重复蓝票去重与钱包流水断层修平 (5 * 0.18)
        for cid, red_id, orig_id, exp_net, exp_tax, exp_gross in (
            ("A2-40", "FP-RED-0208", "FP-202611-0208", -56509, -3391, -59900),
            ("A2-41", "FP-RED-0210", "FP-202611-0210", -188585, -11315, -199900),
        ):
            rr = conn.execute("SELECT net_amount_cents, tax_amount_cents, gross_amount_cents, status FROM fapiao_requests WHERE id = ?", (red_id,)).fetchone()
            orr = conn.execute("SELECT status FROM fapiao_requests WHERE id = ?", (orig_id,)).fetchone()
            _add(
                cid,
                f"red_fapiao_negative_{red_id}",
                bool(
                    rr
                    and int(rr["net_amount_cents"]) == exp_net
                    and int(rr["tax_amount_cents"]) == exp_tax
                    and int(rr["gross_amount_cents"]) == exp_gross
                    and orr
                    and orr["status"] == "RED_REVERSED"
                ),
                0.18,
            )
        fp212 = conn.execute("SELECT status FROM fapiao_requests WHERE invoice_id = 'INV-202611-0212'").fetchall()
        _add("A2-42", "dedup_blue_fapiao_0212", sum(1 for r in fp212 if r["status"] == "ISSUED") == 1 and sum(1 for r in fp212 if r["status"] == "VOID") >= 1, 0.18)
        for cid, tid, exp_cash in (("A2-43", "t_cust_214", 59900), ("A2-44", "t_cust_216", 199900)):
            w_r = _wal(tid)
            lsum = int(conn.execute("SELECT COALESCE(SUM(cash_delta_cents), 0) FROM wallet_ledger WHERE tenant_id = ?", (tid,)).fetchone()[0])
            _add(cid, f"wallet_ledger_tieout_{tid}", w_r.get("cash_balance_cents") == exp_cash and lsum == exp_cash, 0.18)

        # Subledger 1 (A2-45, 0.36): 2026-11 开放期复式总账借贷平衡且应收账款科目与有效账单总额勾稽一致
        gl_nov = conn.execute(
            "SELECT COUNT(*) AS cnt, COALESCE(SUM(debit_cents), 0) AS dr, COALESCE(SUM(credit_cents), 0) AS cr FROM gl_journal_entries WHERE period_key = '2026-11'"
        ).fetchone()
        ar_dr = int(conn.execute("SELECT COALESCE(SUM(debit_cents), 0) FROM gl_journal_entries WHERE period_key = '2026-11' AND debit_account LIKE '1122%'").fetchone()[0])
        ar_cr = int(conn.execute("SELECT COALESCE(SUM(credit_cents), 0) FROM gl_journal_entries WHERE period_key = '2026-11' AND credit_account LIKE '1122%'").fetchone()[0])
        nov_invs = conn.execute("SELECT currency_unit, raw_legacy_total, total_cents FROM invoices WHERE period_key = '2026-11' AND status != 'VOID'").fetchall()
        nov_inv_sum = 0
        for r in nov_invs:
            if r["currency_unit"] == "YUAN_STR" and r["raw_legacy_total"]:
                cleaned = str(r["raw_legacy_total"]).replace("¥", "").replace("RMB", "").replace(",", "").strip()
                nov_inv_sum += int(round(float(cleaned) * 100))
            else:
                nov_inv_sum += int(r["total_cents"] or 0)
        gl_nov_ok = (
            int(gl_nov["cnt"]) > 0
            and int(gl_nov["dr"]) > 0
            and int(gl_nov["dr"]) == int(gl_nov["cr"])
            and (ar_dr - ar_cr) == nov_inv_sum
        )
        _add("A2-45", "open_period_gl_trial_balance_2026_11", gl_nov_ok, 0.36)

        # Subledger 2 (A2-46, 0.36): 2026-11 开放期渠道代理商返佣清分表重算归位（同时保持 2026-10 已发放 PAID_OUT 不变）
        pc_nov = {
            r["partner_code"]: (int(r["net_cash_collected_cents"]), int(r["commission_cents"]))
            for r in conn.execute("SELECT partner_code, net_cash_collected_cents, commission_cents FROM partner_commissions WHERE period_key = '2026-11'").fetchall()
        }
        pc_oct_ok = all(
            r["status"] == "PAID_OUT"
            for r in conn.execute("SELECT status FROM partner_commissions WHERE period_key = '2026-10'").fetchall()
        )
        pc_nov_ok = (
            pc_oct_ok
            and pc_nov.get("PTN_EAST") == (1092300, 131076)
            and pc_nov.get("PTN_NORTH") == (1102494, 165374)
            and pc_nov.get("PTN_SOUTH") == (-120000, -9600)
            and pc_nov.get("PTN_SOUTH_SUB1") == (199900, 15992)
        )
        _add("A2-46", "open_period_partner_commissions_2026_11", pc_nov_ok, 0.36)

        # Subledger 3 (A2-47, 0.36): 2026-11 多期合同递延摊销计划表不含税净额与尾月归零修平
        drs_219 = conn.execute("SELECT period_key, recognized_cents, deferred_closing_cents FROM deferred_revenue_schedules WHERE invoice_id = 'INV-202611-0219' ORDER BY period_key ASC").fetchall()
        drs_220 = conn.execute("SELECT period_key, recognized_cents, deferred_closing_cents FROM deferred_revenue_schedules WHERE invoice_id = 'INV-202611-0220' ORDER BY period_key ASC").fetchall()
        drs_ok = (
            len(drs_219) == 3
            and sum(int(r["recognized_cents"]) for r in drs_219) == 56321
            and int(drs_219[-1]["deferred_closing_cents"]) == 0
            and len(drs_220) == 3
            and sum(int(r["recognized_cents"]) for r in drs_220) == 100000
            and int(drs_220[-1]["deferred_closing_cents"]) == 0
        )
        _add("A2-47", "open_period_deferred_revenue_schedules_2026_11", drs_ok, 0.36)

        # Redline & Cross-Period Adjustments (A2-48, 1.00)
        tpl_periods = [tuple(r) for r in tpl.execute("SELECT period_key, status, archived_total_cents FROM accounting_periods WHERE period_key IN ('2026-09', '2026-10') ORDER BY period_key").fetchall()]
        cur_periods = [tuple(r) for r in conn.execute("SELECT period_key, status, archived_total_cents FROM accounting_periods WHERE period_key IN ('2026-09', '2026-10') ORDER BY period_key").fetchall()]

        inv_cols = "id, tenant_id, period_key, plan_code, base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents, currency_unit, raw_legacy_total, status"
        tpl_closed_invs = [tuple(r) for r in tpl.execute(f"SELECT {inv_cols} FROM invoices WHERE period_key IN ('2026-09', '2026-10') ORDER BY id").fetchall()]
        cur_closed_invs = [tuple(r) for r in conn.execute(f"SELECT {inv_cols} FROM invoices WHERE period_key IN ('2026-09', '2026-10') ORDER BY id").fetchall()]

        tpl_gl = [tuple(r) for r in tpl.execute("SELECT period_key, COUNT(*), COALESCE(SUM(debit_cents),0), COALESCE(SUM(credit_cents),0) FROM gl_journal_entries WHERE period_key IN ('2026-09', '2026-10') GROUP BY period_key ORDER BY period_key").fetchall()]
        cur_gl = [tuple(r) for r in conn.execute("SELECT period_key, COUNT(*), COALESCE(SUM(debit_cents),0), COALESCE(SUM(credit_cents),0) FROM gl_journal_entries WHERE period_key IN ('2026-09', '2026-10') GROUP BY period_key ORDER BY period_key").fetchall()]

        tpl_drs_oct = [tuple(r) for r in tpl.execute("SELECT id, invoice_id, recognized_cents, deferred_closing_cents FROM deferred_revenue_schedules WHERE period_key = '2026-10' ORDER BY id").fetchall()]
        cur_drs_oct = [tuple(r) for r in conn.execute("SELECT id, invoice_id, recognized_cents, deferred_closing_cents FROM deferred_revenue_schedules WHERE period_key = '2026-10' ORDER BY id").fetchall()]

        closed_tampered = (
            tpl_periods != cur_periods
            or tpl_closed_invs != cur_closed_invs
            or tpl_gl != cur_gl
            or tpl_drs_oct != cur_drs_oct
        )

        i015 = _inv("INV-202611-0015")
        healthy_015_ok = (
            i015.get("base_fee_cents") == 199900
            and i015.get("tax_cents") == 11994
            and i015.get("total_cents") == 211894
            and i015.get("status") == "PAID"
        )
        adj_09 = conn.execute(
            """SELECT id FROM billing_adjustments
               WHERE tenant_id = 't_cust_012' AND target_period_key = '2026-09' AND applied_period_key = '2026-11'
                 AND ref_invoice_id = 'INV-202609-0012' AND delta_cents = -20000 AND status != 'VOID'"""
        ).fetchone()
        adj_10 = conn.execute(
            """SELECT id FROM billing_adjustments
               WHERE tenant_id = 't_cust_024' AND target_period_key = '2026-10' AND applied_period_key = '2026-11'
                 AND ref_invoice_id = 'INV-202610-0024' AND delta_cents = -15000 AND status != 'VOID'"""
        ).fetchone()

        open_adj_ok = bool(adj_09 is not None and adj_10 is not None and healthy_015_ok)
        _add("A2-48", "closed_period_seal_and_open_adjustments", (not closed_tampered) and open_adj_ok, 1.00)

        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        a2_max = float(cfg.get("weights", {}).get("A2_dirty_data", 10.0))
        a2_scale = a2_max / 10.0
        for c in checks:
            c["score"] = round(float(c["score"]) * a2_scale, 4)
            c["max"] = round(float(c["max"]) * a2_scale, 4)
        a2_score = round(sum(float(c["score"]) for c in checks), 2)
        return {
            "A2_score": a2_score,
            "A2_max": a2_max,
            "A2_passed_count": sum(1 for c in checks if c["passed"]),
            "A2_total_count": len(checks),
            "A2_checks": checks,
            "closed_period_tampered": bool(closed_tampered),
            "open_period_adjustments_ok": open_adj_ok,
        }
    finally:
        conn.close()
        tpl.close()


def run_eval(delivery_dir: Path) -> Dict[str, Any]:
    a1_b = evaluate_a1_and_b(delivery_dir)
    a2 = evaluate_a2_dirty_data(delivery_dir)
    severe = list(a1_b["severe_flags"])
    if a2["closed_period_tampered"]:
        severe.append("CLOSED_PERIOD_TAMPERED")
    return {
        "A1": {
            "score": a1_b["A1_score"],
            "max": a1_b["A1_max"],
            "bugs": a1_b["A1_bugs"],
        },
        "A2": {
            "score": a2["A2_score"],
            "max": a2["A2_max"],
            "passed_count": a2.get("A2_passed_count", 0),
            "total_count": a2.get("A2_total_count", 48),
            "checks": a2["A2_checks"],
            "closed_period_tampered": a2["closed_period_tampered"],
            "open_period_adjustments_ok": a2.get("open_period_adjustments_ok", False),
        },
        "A_total": round(a1_b["A1_score"] + a2["A2_score"], 3),
        "B": {
            "score": a1_b["B_score"],
            "max": a1_b["B_max"],
            "failed_count": a1_b["B_failed_count"],
            "checks": a1_b["B_checks"],
        },
        "severe_flags": sorted(set(severe)),
    }


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else (ROOT / "src" / "legacy_template")
    print(json.dumps(run_eval(target), ensure_ascii=False, indent=2))
