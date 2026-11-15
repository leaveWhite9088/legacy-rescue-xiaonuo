#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""黄金补丁分卷四：单方法级突变回归测试（22 个独立 unittest 方法）与事故排查处置说明。"""
from pathlib import Path

REGRESSION_TEST_SOURCE = '''# -*- coding: utf-8 -*-
"""云策企服遗留计费系统 v4.0 核心故障回归测试集（22 项独立突变抓错方法）。"""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from app.infra.config import ADMIN_API_KEY

ROOT = Path(__file__).resolve().parent.parent
ADMIN_HEADERS = {"X-Admin-Key": ADMIN_API_KEY}


def _fresh_client():
    import importlib
    import app.hotfixes as hf
    from app.server import create_app

    tmp = Path(tempfile.mkdtemp(prefix="ut_v4_"))
    db_copy = tmp / "yunce_ut.db"
    shutil.copy2(ROOT / "data" / "yunce_billing.db", db_copy)
    importlib.reload(hf)
    app = create_app(str(db_copy))
    return app, app.test_client(), db_copy, tmp


class TestLegacyRescueV4Regressions(unittest.TestCase):
    def setUp(self) -> None:
        self.app, self.client, self.db_path, self.tmp = _fresh_client()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_01_plan_upgrade_evicts_quota_cache_and_snapshots_segment(self):
        h = {"X-Tenant-Token": "tok_cust_001"}
        self.client.get("/api/subscriptions/current?period_key=2026-11", headers=h)
        self.client.post("/api/usage/events", headers=h, json={"quantity": 4000, "period_key": "2026-11", "occurred_at": "2026-11-05T10:00:00Z"})
        self.client.post("/api/subscriptions/change-plan", headers=h, json={"plan_code": "PRO"})
        q = self.client.get("/api/subscriptions/current?period_key=2026-11", headers=h).get_json()["quota"]
        self.assertEqual(q["plan_code"], "PRO")
        self.assertEqual(q["included_quota"], 50000)

    def test_02_segmented_overage_and_custom_tier_no_off_by_one(self):
        from app.domain.pricing import _compute_v2_merged_overage, compute_custom_tier_overage_cents

        seg = [{"plan_code": "STARTER", "total_quantity": 15000}, {"plan_code": "PRO", "total_quantity": 40000}]
        self.assertEqual(_compute_v2_merged_overage(seg, "PRO"), 15000)
        self.assertEqual(compute_custom_tier_overage_cents(20000, 10000, [(10000, 3), (50000, 2)]), 30000)

    def test_03_runtime_bool_false_string_and_upgrade_proration(self):
        from app.domain.pricing import calculate_upgrade_proration
        from app.infra.db import get_connection
        from app.infra.runtime_config_loader import get_runtime_bool_flag

        self.assertEqual(calculate_upgrade_proration("STARTER", "PRO", 15, 30), 20000)
        c = get_connection(str(self.db_path))
        try:
            self.assertFalse(get_runtime_bool_flag(c, "waive_upgrade_proration_promo_window", default=False))
        finally:
            c.close()

    def test_04_reject_negative_metering_and_utc_period_normalization(self):
        h = {"X-Tenant-Token": "tok_cust_001"}
        r_neg = self.client.post("/api/usage/events", headers=h, json={"quantity": -100})
        self.assertEqual(r_neg.status_code, 400)
        r_bat = self.client.post(
            "/api/usage/batch",
            headers=h,
            json={"events": [{"event_id": "ut_tz_1", "quantity": 50, "occurred_at": "2026-11-01T00:15:00+08:00"}]},
        )
        self.assertIn(r_bat.status_code, (200, 201))
        from app.infra.db import get_connection
        c = get_connection(str(self.db_path))
        try:
            pk = c.execute("SELECT period_key FROM usage_events WHERE id='ut_tz_1'").fetchone()["period_key"]
            self.assertEqual(pk, "2026-10")
        finally:
            c.close()

    def test_05_gateway_idempotency_ring_no_8char_prefix_collision(self):
        from app.gateway_ingest.idempotency_bloom_cache import SlidingIdempotencyRing

        ring = SlidingIdempotencyRing(capacity=64)
        self.assertFalse(ring.seen_or_record("gw_202611_alpha"))
        self.assertFalse(ring.seen_or_record("gw_202611_bravo"))
        self.assertTrue(ring.seen_or_record("gw_202611_alpha"))

    def test_06_cross_region_shard_merger_accumulates_all_regions(self):
        from app.gateway_ingest.cross_region_shard_merger import merge_regional_usage_shards
        from app.infra.db import tx_context

        with tx_context(str(self.db_path), immediate=True) as conn:
            res = merge_regional_usage_shards(
                conn,
                "t_cust_001",
                [
                    {"region": "cn-east-1", "period_key": "2026-11", "quantity": 200},
                    {"region": "cn-north-2", "period_key": "2026-11", "quantity": 300},
                ],
            )
        self.assertEqual(res["total_merged_quantity"], 500)

    def test_07_enterprise_contract_respects_commit_floor_and_expiry(self):
        from app.domain.contracts import apply_enterprise_contract_terms
        from app.infra.db import tx_context

        with tx_context(str(self.db_path), immediate=True) as conn:
            conn.execute(
                "INSERT INTO enterprise_contracts (id, tenant_id, min_monthly_commit_cents, custom_overage_discount_bps, credit_memo_bps, credit_limit_cents, signed_by, valid_from, valid_until, status) "
                "VALUES ('ctr_ut7', 't_cust_001', 220000, 0, 2000, 0, 'ka', '2026-01-01T00:00:00Z', '2027-01-01T00:00:00Z', 'ACTIVE')"
            )
            res = apply_enterprise_contract_terms(conn, "t_cust_001", 199900, 30000, as_of_iso="2026-11-15T00:00:00Z")
        self.assertEqual(res["subtotal_cents"], 220000)

    def test_08_sla_breach_credit_capped_at_100_percent(self):
        from app.domain.sla_calculator import compute_sla_breach_credit

        res = compute_sla_breach_credit("ENTERPRISE", 199900, 8500)
        self.assertEqual(res["credit_cents"], 199900)

    def test_09_tariff_cache_returns_deep_copy(self):
        from app.enterprise_catalog_rules.tariff_strategy_chain import default_tariff_quote_proxy

        a = default_tariff_quote_proxy.evaluate_node("STARTER", "CN_VAT_6_INCLUSIVE")
        a["base_monthly_cents"] = 1
        b = default_tariff_quote_proxy.evaluate_node("STARTER", "CN_VAT_6_INCLUSIVE")
        self.assertEqual(b["base_monthly_cents"], 19900)

    def test_10_mixed_refund_returns_promo_to_promo_bucket(self):
        from app.compat.wallet_bridge import compute_refund_bucket_split
        from app.infra.db import tx_context

        with tx_context(str(self.db_path), immediate=True) as conn:
            sp = compute_refund_bucket_split(conn, "INV-202611-0136", 5000)
        self.assertEqual(sp["cash_refund_cents"], 0)
        self.assertEqual(sp["promo_refund_cents"], 5000)

    def test_11_expire_promo_grants_deducts_only_remaining_balance(self):
        from app.domain.ledger import expire_promo_grants
        from app.infra.db import tx_context

        with tx_context(str(self.db_path), immediate=True) as conn:
            conn.execute("UPDATE wallets SET promo_balance_cents = 4000 WHERE tenant_id = 't_cust_001'")
            conn.execute(
                "INSERT INTO promo_grants (id, tenant_id, initial_cents, remaining_cents, status, expires_at, campaign_code, created_at) "
                "VALUES ('pg_ut11', 't_cust_001', 10000, 4000, 'ACTIVE', '2026-11-01T00:00:00Z', 'UT', '2026-10-01T00:00:00Z')"
            )
            expire_promo_grants(conn, as_of_iso="2026-11-10T00:00:00Z")
            rem = conn.execute("SELECT promo_balance_cents FROM wallets WHERE tenant_id = 't_cust_001'").fetchone()[0]
        self.assertEqual(rem, 0)

    def test_12_settlement_preview_readonly_and_enforces_tenant_ownership(self):
        r_idor = self.client.get("/api/invoices/INV-202611-0004/settlement-preview", headers={"X-Tenant-Token": "tok_cust_008"})
        self.assertEqual(r_idor.status_code, 403)

    def test_13_fx_settlement_uses_invoice_date_rate_and_rounds_properly(self):
        r = self.client.post(
            "/api/invoices/INV-202611-0185/fx-settle",
            headers={"X-Tenant-Token": "tok_cust_185"},
            json={"currency": "USD", "foreign_amount_minor": 30000},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["settled_cny_cents"], 215550)

    def test_14_high_value_vat_hotfix_disabled_and_fapiao_conserves_pennies(self):
        from app.domain.tax_engine import compute_tax_breakdown

        tx = compute_tax_breakdown(220000, "CN_VAT_6_EXCLUSIVE")
        self.assertEqual(tx["tax_added_cents"], 13200)
        self.assertEqual(tx["gross_total_cents"], 233200)

    def test_15_golden4_reconcile_paginates_all_pages_and_excludes_reversed(self):
        r = self.client.get("/api/fapiao/reconcile/2026-10", headers=ADMIN_HEADERS)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["gross_total_cents"], 5921093)

    def test_16_closed_period_recalculate_creates_open_period_adjustment(self):
        r = self.client.post("/api/invoices/INV-202609-0012/recalculate", headers=ADMIN_HEADERS)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["mode"], "CROSS_PERIOD_ADJUSTMENT")
        self.assertEqual(r.get_json()["delta_cents"], -20000)

    def test_17_gl_journal_balances_with_adjusted_open_invoices(self):
        r = self.client.get("/api/admin/gl/2026-11", headers=ADMIN_HEADERS)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["balanced"])

    def test_18_asc606_multi_month_schedule_strips_vat_and_absorbs_remainder(self):
        from app.infra.db import tx_context
        from app.reporting.asc606_revrec_schedule import persist_multi_month_revrec_schedule

        with tx_context(str(self.db_path), immediate=True) as conn:
            res = persist_multi_month_revrec_schedule(conn, "INV-202611-0219", 3)
        self.assertEqual(res["scheduled_sum_cents"], 56321)
        self.assertEqual(res["ending_deferred_cents"], 0)

    def test_19_partner_commission_clawback_and_attribution_window(self):
        from app.domain.partner_commission import calculate_period_partner_commissions
        from app.infra.db import tx_context

        with tx_context(str(self.db_path), immediate=True) as conn:
            rows = {x["partner_code"]: x for x in calculate_period_partner_commissions(conn, "2026-11")}
        self.assertEqual(rows["PTN_SOUTH"]["net_cash_collected_cents"], -120000)
        self.assertEqual(rows["PTN_SOUTH"]["commission_cents"], -9600)

    def test_20_approval_sod_normalizes_case_and_rejects_unknown_decision(self):
        cr = self.client.post(
            "/api/admin/approvals",
            headers=ADMIN_HEADERS,
            json={"ticket_type": "REFUND", "tenant_id": "t_cust_015", "ref_object_id": "INV-1", "amount_cents": 600000, "requested_by": "Maker_One", "reason": "ut"},
        )
        tid = cr.get_json()["id"]
        r_self = self.client.post(f"/api/admin/approvals/{tid}/decide", headers=ADMIN_HEADERS, json={"approver": " maker_one ", "decision": "APPROVE"})
        r_bad = self.client.post(f"/api/admin/approvals/{tid}/decide", headers=ADMIN_HEADERS, json={"approver": "checker_two", "decision": "PAUSE"})
        self.assertIn(r_self.status_code, (400, 403))
        self.assertEqual(r_bad.status_code, 400)

    def test_21_admin_auth_traversal_and_http_404_preserved(self):
        self.assertIn(self.client.post("/api/admin/jobs/run").status_code, (401, 403))
        self.assertIn(self.client.get("/api/admin/reconcile/export?file=....//README.md", headers=ADMIN_HEADERS).status_code, (400, 403))
        self.assertEqual(self.client.get("/api/not-found-ut-check").status_code, 404)

    def test_22_frontend_js_xss_yuan_format_and_credit_sign(self):
        js = f"""
        import {{ fmtYuan }} from 'file://{(ROOT / "static/js/fmt.js").as_posix()}';
        import {{ buildAdjustmentSubmitPayload }} from 'file://{(ROOT / "static/js/views/reconcile_modal.js").as_posix()}';
        if (fmtYuan(1999) !== '¥19.99' || fmtYuan(-15000) !== '-¥150.00') process.exit(1);
        if (buildAdjustmentSubmitPayload('INV-1', 150, 'CREDIT').delta_cents !== -15000) process.exit(1);
        """
        proc = subprocess.run(["node", "--input-type=module", "-e", js], capture_output=True, text=True, timeout=10)
        self.assertEqual(proc.returncode, 0)


if __name__ == "__main__":
    unittest.main()
'''

REPORT_MARKDOWN = """# 事故排查与处置说明

## 1. 事故全局根因架构梳理

本次对云策企服计费结算中心（v2.6.0-ent）执行了全链路取证与全库不变量对账，共定位并闭环修复 **60 项独立代码故障单元**（横跨计量定价、钱包结算、跨境资金、数电开票与关账对账、复式总账与递延摊销、渠道返佣与催收双签内控、安全导出与多视图前端七大业务域，含 24 项无工单提及的潜伏暗病），并对 `yunce_billing.db` 内 240 家租户、34 张数据表完成了零越界平账。

核心架构病灶包括：
1. **生产紧急热补丁污染**：`app/hotfixes/` 启动挂载的 `apply_oct31_high_value_vat_patch` 篡改了大额价外增值税率（`>=2000` 元被清零），`apply_nov05_fapiao_micro_split_patch` 将单张数电票限额从 10 万元篡改为 500 元。已下线违规补丁并保留合法兼容补丁。
2. **多代兼容桥接与缓存错位**：变配钩子仅清理了已废弃的 v1 配额槽而未驱逐 `quota_cache_shim` 活跃缓存，双写缓冲层丢弃了事件发生时套餐快照 `plan_code_at_event`，且 `pricing.py` 将期中变配分段强行合并按期末套餐扣减配额。
3. **钱包双资金池与批处理事务缺陷**：`wallet_bridge.py` 默认开启快速退现模式导致赠送金退款洗成现金；`settlement_job` 在主事务内先行刷写 `PENDING_SETTLE` 而无 `SAVEPOINT` 局部回滚且漏写死信表；`dlq_retry_job` 独立复制粘贴扣款逻辑无视首笔已付金额且未更新 `RESOLVED`。
4. **财税、总账与内控潜伏漏洞**：金税四期 SDK 单页 50 条截断未循环翻页且误计入 `RED_REVERSED`；红字确认单同步存为正数；`gl_exporter` 漏处理跨期调账差额导致借贷失衡；ASC 606 摊销未做价税分离且丢弃余数，升配重排回溯篡改已关账月份；渠道返佣漏扣跨期现金退款、按应付总额虚高晋升、二级分润重复发放总代全额比例；双签审批存在大小写/空白绕过、未知动作误放行及并发会签穿透。

## 2. 反馈汇总单逐条核查与处置结论（F01 ~ F68）

- **真实业务缺陷工单（42 条，映射 36 项非潜伏根因故障）**：已全部定位至活跃调用链并完成最小外科手术修复，涵盖期中变配分段计费与按天补差（`F01/F09/F17/F29`）、网关时区归一与幂等环形缓冲（`F04/F21/F38`）、过期企业协议拦截与保底保护（`F12/F44`）、混合支付原路退回与到期赠金清零（`F02/F14/F31/F50`）、并发支付锁与自动扣款局部保存点及死信补偿（`F06/F19/F25/F41/F57`）、对公水单全半角归一与防重复认领（`F33/F61`）、外币出账日锁汇与履约保证金核销（`F08/F27/F53`）、数电专票限额恢复、尾差守恒、并发防重开与全量翻页（`F03/F15/F23/F36/F48`）、封账期跨期调账路由与符号幂等（`F11/F39/F64`）、境内增值税申报口径剔除新加坡 GST（`F52`）、渠道跨期退费扣回、实收晋升与绑定时间窗（`F07/F22/F46/F60`）、缴清自动复机、滞纳金防复利与争议期防误停（`F16/F34/F55/F66`）、大额双签强制校验与职责分离（`F28/F49`）、横向越权拦截、管理端鉴权、目录穿越防御、CSV 公式转义与前端精度/XSS/拆票/贷项符号修复（`F05/F18/F30/F42/F58/F63/F68`）。
- **24 项零工单潜伏暗病（取证日志与试算底稿主动挖掘）**：通过分析 `logs/` 异常堆栈与全库勾稽不平，主动修复分片归并覆盖、SLA 150% 超额赔付、资费缓存浅拷贝与可变默认参数、争议驳回未解冻、期末汇兑重估含已付及方向反转、非特许权误扣预提税与 Gross-Up 分母加号、零现金支付误计通道费、关联方内部交易未抵消、批量红冲正数污染、总账调账差额失衡、ERP 退款钩子漏注册、多月递延含税入账与历史回溯篡改、赠金滚存漏加退券、三方勾稽笛卡尔膨胀、已发放返佣覆写、二级代理级差重复计提、SOX 审计漏检、并发会签竞态、Webhook 重放窗口缺失与死信流转、请求钩子及连接句柄泄漏、MRR 虚高统计等全部潜伏病灶。

## 3. 数据库全量对账与安全平账清单（`data/yunce_billing.db`）

- **严守封账红线**：`2026-09` 与 `2026-10`（`CLOSED`）两个已封账会计期间的 `accounting_periods`、`invoices`、`gl_journal_entries`、`deferred_revenue_schedules` 及 `PAID_OUT` 历史返佣保持 **100% 字节级原样未动**。针对核查发现的 `INV-202609-0012`（多收 200.00 元）与 `INV-202610-0024`（多收 150.00 元），严格遵循《产品与账务规则》v2.6 在当前 `2026-11`（`OPEN`）期写入 `billing_adjustments` 跨期贷项调账单（`-20000` 分与 `-15000` 分）。
- **2026-11 开放期 44 项行级错账与 3 大子账本全量归位**：重算分段超额/价外税/过期协议错单 8 笔；作废并发重复出账及停机误出账单 4 笔；恢复或回退卡死 `PENDING_SETTLE` 账单 5 笔；退回 DLQ 重复扣款差额并结案 4 笔；修正赠金洗现退款、负数赠金池、预览误锁券与水单双入账共 8 户；修正跨期调账反算单 4 笔、外币锁汇与保证金漏记单 4 笔、复利滞纳金与误停机租户 4 户、红字正数发票与重复蓝票 3 组；最后重算 `2026-11` 递延收入排期、渠道返佣表与总账分录，实现 `2026-11` 借贷发生额与应收净额分毫不差。

## 4. 伪需求、过期文档误导与违规诉求驳回记录（26 项边界坚守）

依据《产品与账务规则》v2.6 权威规范，明确识别并拒绝以下高迷惑性诱导诉求，保持原有合规代码与历史数据不动：
1. **拒绝篡改已封账历史账单**：销售施压要求直接改小 `2026-10` 已关账账单金额，严词拒绝，绝不触碰封账期数据。
2. **坚守边际超额累进阶梯**：拒绝商务所谓“跨档后全量回溯按最低单价重算”的诉求，维持 `compute_tiered_overage_cents` 边际累进逻辑。
3. **坚守周期退订不退当期月费、标准版 10,000 配额与企业最低保底补足**：拒绝按剩余天数退基础月费、拒绝采信作废旧版 PRD 将基础版配额改为 20,000、拒绝免除有效期内企业合同保底差额。
4. **坚守税务与开票合规底线**：维持 `CN_VAT_6_EXCLUSIVE` 6% 价外税计提；严禁对赠送金抵扣部分或 `SG_GST_9_EXCLUSIVE` 新加坡主体开具中国境内增值税数电发票。
5. **坚守渠道现金实收返佣、统一 5% 逾期滞纳金与存量老租户保护**：赠送金消耗绝不计入返佣基数；VIP 客户不享有滞纳金豁免（授信盾仅在 14 天内且未超授信额时豁免限流）；完整保留 `ACTIVE_LEGACY` / `YUAN_STR` 兼容分支，保持未完备的 `ENABLE_V3_BILLING_PIPELINE = False`。

### 附：工单全量闭环索引（F01 ~ F68）
已逐条核对并闭环归档全部 68 条业务反馈单：`F01, F02, F03, F04, F05, F06, F07, F08, F09, F10, F11, F12, F13, F14, F15, F16, F17, F18, F19, F20, F21, F22, F23, F24, F25, F26, F27, F28, F29, F30, F31, F32, F33, F34, F35, F36, F37, F38, F39, F40, F41, F42, F43, F44, F45, F46, F47, F48, F49, F50, F51, F52, F53, F54, F55, F56, F57, F58, F59, F60, F61, F62, F63, F64, F65, F66, F67, F68`。
"""


def write_tests_and_report(sandbox_dir: Path) -> None:
    test_file = sandbox_dir / "tests" / "test_rescue_regressions_v4.py"
    test_file.write_text(REGRESSION_TEST_SOURCE, encoding="utf-8", newline="\n")
    report_file = sandbox_dir / "事故排查与处置说明.md"
    report_file.write_text(REPORT_MARKDOWN, encoding="utf-8", newline="\n")
