#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""事故现场资产构建器（驻留主控构建目录，绝不拷贝进选手沙盒）：
生成 128 租户规模的 SQLite 线上快照 (yunce_billing.db) 与 2700+ 行三日生产日志。
"""
import json
import os
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATE_DIR = ROOT / "src" / "legacy_template"
sys.path.insert(0, str(TEMPLATE_DIR))

from app.domain.gl_exporter import generate_gl_entries_for_period  # noqa: E402
from app.domain.partner_commission import calculate_period_partner_commissions  # noqa: E402
from app.domain.pricing import compute_tiered_overage_cents  # noqa: E402
from app.domain.tax_engine import compute_tax_breakdown  # noqa: E402
from app.infra.config import PLANS  # noqa: E402
from app.infra.db import get_connection, init_schema, parse_legacy_amount_cents  # noqa: E402

COMPANY_PREFIXES = [
    "云帆", "星图", "智联", "华辰", "博远", "天枢", "锦程", "山海", "乾元", "中科",
    "万象", "晨曦", "纵横", "远景", "宏图", "百川", "启明", "凌云", "沧海", "金盾",
]
COMPANY_SUFFIXES = [
    "数据科技", "智能制造", "供应链", "数字零售", "云计算", "生物医药", "跨境电商", "物联网", "信息安全", "企业服务",
]

SPECIAL_NAMES = {
    "t_cust_005": "极光电商",
    "t_cust_008": "青禾数字",
    "t_cust_012": "智汇云科技",
    "t_cust_015": "盛世跨境科技",
    "t_cust_019": "云图数据",
    "t_cust_034": "蓝海智造",
    "t_cust_051": "飞跃零售",
    "t_cust_067": "锐捷医疗",
    "t_cust_078": "星河传媒",
    "t_cust_083": "瀚海物联",
    "t_cust_092": "千帆供应链",
}


def build_database() -> dict:
    rng = random.Random(20261114)
    db_path = str(TEMPLATE_DIR / "data" / "yunce_billing.db")
    if os.path.exists(db_path):
        os.remove(db_path)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    conn = get_connection(db_path)
    try:
        init_schema(conn)

        # ------------------------------------------------------------------
        # 1. 创建 15 个 2024 v1 存量老租户 (t_leg_001 .. t_leg_015)
        # ------------------------------------------------------------------
        legacy_names = [
            "华东老牌制造集团", "星辰传统物流", "南洋纺织实业", "北方重工机械", "长三角塑化贸易",
            "津门港务货运", "中原农机配件", "宏达五金建材", "海燕日化集团", "顺发纸业包装",
            "恒信模具加工", "永泰食品冷链", "国瑞电缆制造", "振华陶瓷工艺", "昌盛汽配连锁",
        ]
        for i in range(1, 16):
            tid = f"t_leg_{i:03d}"
            disc_bps = 1000 if i == 1 else (500 if i % 3 == 0 else 0)
            meta = json.dumps({"legacy_discount_bps": disc_bps, "migrated_from": "erp_2024_q4"})
            conn.execute(
                """INSERT INTO tenants (id, company_name, api_token, status, tier_level, tax_profile_code,
                   partner_code, webhook_url, schema_version, billing_metadata, created_at)
                   VALUES (?, ?, ?, 'ACTIVE_LEGACY', 'STANDARD', 'EXEMPT', NULL, '', 1, ?, ?)""",
                (tid, legacy_names[i - 1], f"tok_leg_{i:03d}", meta, f"2024-0{(i % 8) + 1}-10T00:00:00Z"),
            )
            override = None
            if i == 1:
                override = json.dumps({"fixed_fee_cents": 9900, "included_quota": 20000, "overage_cap_cents": 5000})
            elif i % 4 == 0:
                override = json.dumps({"fixed_fee_cents": 8800, "included_quota": 25000})

            conn.execute(
                """INSERT INTO subscriptions (id, tenant_id, plan_code, status, cycle_start, cycle_end,
                   next_billing_at, auto_renew, tier_mode, legacy_contract_override, updated_at)
                   VALUES (?, ?, 'LEGACY_FLAT_99', 'ACTIVE_LEGACY', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z',
                   '2026-12-01T00:00:00Z', 1, NULL, ?, '2026-11-01T00:00:00Z')""",
                (f"sub_leg_{i:03d}", tid, override),
            )
            cash = 40000 + i * 2500
            conn.execute(
                "INSERT INTO wallets (tenant_id, cash_balance_cents, promo_balance_cents, updated_at) VALUES (?, ?, 0, '2026-11-01T00:00:00Z')",
                (tid, cash),
            )
            conn.execute(
                "INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES (?, 'TOPUP', ?, 0, ?, '初始结转充值', '2026-08-25T08:00:00Z')",
                (tid, cash + 20000, f"top_leg_{i:03d}"),
            )

            # 2026-09 历史 v1 字符串元账单
            fee_09 = 8910 if i == 1 else (8800 if i % 4 == 0 else (9405 if i % 3 == 0 else 9900))
            yuan_str = f"{fee_09 // 100}.{fee_09 % 100:02d}"
            inv_09_id = f"INV-202609-L{i:03d}"
            conn.execute(
                """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
                   base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
                   currency_unit, raw_legacy_total, status, dispute_reason, created_at, updated_at)
                   VALUES (?, ?, '2026-09', '2026-09-01T00:00:00Z', '2026-10-01T00:00:00Z', 'LEGACY_FLAT_99',
                   ?, 0, 0, 0, ?, ?, 0, 'YUAN_STR', ?, 'PAID', '', '2026-09-30T23:00:00Z', '2026-10-01T00:10:00Z')""",
                (inv_09_id, tid, fee_09, fee_09, fee_09, yuan_str),
            )
            conn.execute(
                "INSERT INTO invoice_payments (id, invoice_id, tenant_id, idempotency_key, cash_paid_cents, promo_paid_cents, total_paid_cents, created_at) VALUES (?, ?, ?, ?, ?, 0, ?, '2026-10-01T00:10:00Z')",
                (f"pay_09_l{i:03d}", inv_09_id, tid, f"leg09:{inv_09_id}", fee_09, fee_09),
            )
            conn.execute(
                "INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES (?, 'INVOICE_PAY', ?, 0, ?, '9月老合同扣款', '2026-10-01T00:10:00Z')",
                (tid, -fee_09, inv_09_id),
            )

        # ------------------------------------------------------------------
        # 2. 创建 113 个 v2 现代租户 (t_cust_001 .. t_cust_113)
        # ------------------------------------------------------------------
        special_ids = {19, 34, 51, 67, 78, 83, 92}
        partners = [("PTN_EAST", "GOLD"), ("PTN_SOUTH", "SILVER"), ("PTN_NORTH", "PLATINUM")]

        for i in range(1, 114):
            tid = f"t_cust_{i:03d}"
            cname = SPECIAL_NAMES.get(
                tid,
                f"{COMPANY_PREFIXES[i % len(COMPANY_PREFIXES)]}{COMPANY_SUFFIXES[(i * 3) % len(COMPANY_SUFFIXES)]}{i:02d}",
            )

            # 套餐与等级分布
            if tid in ("t_cust_005", "t_cust_012", "t_cust_015", "t_cust_034", "t_cust_092"):
                plan_code = "PRO"
            elif tid in ("t_cust_008", "t_cust_019", "t_cust_051", "t_cust_067", "t_cust_078", "t_cust_083"):
                plan_code = "STARTER"
            else:
                plan_code = ["STARTER", "STARTER", "PRO", "PRO", "ENTERPRISE"][i % 5]

            tier_level = "VIP" if (plan_code == "ENTERPRISE" or tid in ("t_cust_005", "t_cust_012")) else "STANDARD"
            if i in special_ids or tid in ("t_cust_005", "t_cust_008", "t_cust_012"):
                tax_code = "CN_VAT_6_INCLUSIVE"
            elif tid == "t_cust_015" or i % 17 == 0:
                tax_code = "CN_VAT_6_EXCLUSIVE"
            elif i % 29 == 0:
                tax_code = "SG_GST_9_EXCLUSIVE"
            else:
                tax_code = "CN_VAT_6_INCLUSIVE"
            p_info = partners[i % 3] if i % 4 == 0 else None
            wh_url = f"https://hooks.customer-{i:03d}.example.com/billing" if i % 5 == 0 else ""

            conn.execute(
                """INSERT INTO tenants (id, company_name, api_token, status, tier_level, tax_profile_code,
                   partner_code, webhook_url, schema_version, billing_metadata, created_at)
                   VALUES (?, ?, ?, 'ACTIVE', ?, ?, ?, ?, 2, '{}', ?)""",
                (
                    tid,
                    cname,
                    f"tok_cust_{i:03d}",
                    tier_level,
                    tax_code,
                    p_info[0] if p_info else None,
                    wh_url,
                    f"2025-{(i % 12) + 1:02d}-{(i % 25) + 1:02d}T08:00:00Z",
                ),
            )
            if p_info:
                conn.execute(
                    "INSERT INTO partner_referrals (partner_code, tenant_id, partner_tier, bound_at) VALUES (?, ?, ?, '2025-06-01T00:00:00Z')",
                    (p_info[0], tid, p_info[1]),
                )

            # 部分 ENTERPRISE 签有最低保底框架合同
            if plan_code == "ENTERPRISE" and i % 10 == 4:
                conn.execute(
                    """INSERT INTO enterprise_contracts (id, tenant_id, min_monthly_commit_cents, custom_overage_discount_bps,
                       credit_limit_cents, signed_by, valid_from, valid_until, status)
                       VALUES (?, ?, 220000, 1000, 500000, 'ka_director', '2026-01-01T00:00:00Z', '2027-01-01T00:00:00Z', 'ACTIVE')""",
                    (f"ctr_{i:03d}", tid),
                )

            sub_updated = "2026-11-10T10:00:00Z" if tid == "t_cust_019" else (
                "2026-11-08T14:00:00Z" if tid == "t_cust_083" else "2026-11-01T00:00:00Z"
            )
            conn.execute(
                """INSERT INTO subscriptions (id, tenant_id, plan_code, status, cycle_start, cycle_end,
                   next_billing_at, auto_renew, tier_mode, legacy_contract_override, updated_at)
                   VALUES (?, ?, ?, 'ACTIVE', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z',
                   '2026-12-01T00:00:00Z', 1, 'PROGRESSIVE', NULL, ?)""",
                (f"sub_cust_{i:03d}", tid, plan_code, sub_updated),
            )

            # 若非特殊受灾户，生成健康一致的钱包、历史账单与当期数据
            if i not in special_ids:
                init_topup = 300000 if plan_code == "ENTERPRISE" else (180000 if plan_code == "PRO" else 80000)
                cash_bal = init_topup
                promo_bal = 0
                conn.execute(
                    "INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES (?, 'TOPUP', ?, 0, ?, '银行公户充值', '2026-09-01T09:00:00Z')",
                    (tid, init_topup, f"top_init_{i:03d}"),
                )

                if tid == "t_cust_008":
                    promo_bal = 10000
                    conn.execute(
                        "INSERT INTO promo_grants (id, tenant_id, initial_cents, remaining_cents, status, expires_at, campaign_code, created_at) VALUES ('pg_cust_008', ?, 10000, 10000, 'ACTIVE', '2026-12-31T23:59:59Z', 'Q4_RETENTION', '2026-11-01T00:00:00Z')",
                        (tid,),
                    )
                    conn.execute(
                        "INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES (?, 'PROMO_GRANT', 0, 10000, 'pg_cust_008', '活动赠送金', '2026-11-01T00:00:00Z')",
                        (tid,),
                    )

                # 生成 2026-09 与 2026-10 已结清账单
                for m_idx, pk in enumerate(("2026-09", "2026-10")):
                    if i % 2 != m_idx % 2 and tid not in ("t_cust_005", "t_cust_012", "t_cust_015"):
                        continue
                    pl = PLANS[plan_code]
                    qty = rng.randint(2000, pl["included_quota"] + 15000)
                    if tid == "t_cust_005" and pk == "2026-10":
                        qty = 120000  # F11 伪反馈案例：PRO 含5万，用12万，超7万 -> 50000*2 + 20000*1 = 120000
                    elif tid == "t_cust_012" and pk == "2026-09":
                        qty = 70000  # 实际超 20000 次 -> 应为 40000 分，但历史错收了 60000 分（多收 20000 分）
                    conn.execute(
                        "INSERT INTO usage_summaries (tenant_id, period_key, plan_code, total_quantity, updated_at) VALUES (?, ?, ?, ?, ?)",
                        (tid, pk, plan_code, qty, f"{pk}-28T23:00:00Z"),
                    )
                    ov = compute_tiered_overage_cents(qty, pl["included_quota"], pl["overage_tiers"])
                    base = pl["monthly_fee_cents"]
                    if tid == "t_cust_012" and pk == "2026-09":
                        # F09 已封账历史多收 200 元差额案例 (INV-202609-0012)
                        inv_id = "INV-202609-0012"
                        ov = 60000
                        tax_c = 0
                        tot = base + ov
                        disp = "9月历史超额核算多收200元，账期已关账待跨期冲抵"
                    else:
                        inv_id = f"INV-{pk.replace('-', '')}-{i:04d}"
                        tx = compute_tax_breakdown(base + ov, tax_code)
                        tax_c = tx["tax_added_cents"]
                        tot = tx["gross_total_cents"]
                        disp = ""

                    # 确保钱包够扣
                    if cash_bal < tot + 50000:
                        extra = 300000
                        cash_bal += extra
                        conn.execute(
                            "INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES (?, 'TOPUP', ?, 0, ?, '续费补充值', ?)",
                            (tid, extra, f"top_{pk}_{i:03d}", f"{pk}-25T10:00:00Z"),
                        )

                    cash_bal -= tot
                    conn.execute(
                        """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
                           base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
                           currency_unit, status, dispute_reason, created_at, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, 0, 'CENTS', 'PAID', ?, ?, ?)""",
                        (inv_id, tid, pk, f"{pk}-01T00:00:00Z", f"{pk}-30T23:59:59Z", plan_code, base, ov, tax_c, tot, tot, disp, f"{pk}-29T00:00:00Z", f"{pk}-29T01:00:00Z"),
                    )
                    conn.execute(
                        "INSERT INTO invoice_payments (id, invoice_id, tenant_id, idempotency_key, cash_paid_cents, promo_paid_cents, total_paid_cents, created_at) VALUES (?, ?, ?, ?, ?, 0, ?, ?)",
                        (f"pay_{pk}_{i:03d}", inv_id, tid, f"auto:{inv_id}", tot, tot, f"{pk}-29T01:00:00Z"),
                    )
                    conn.execute(
                        "INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES (?, 'INVOICE_PAY', ?, 0, ?, ?, ?)",
                        (tid, -tot, inv_id, f"支付账单 {inv_id}", f"{pk}-29T01:00:00Z"),
                    )

                # 生成 2026-11 当期正常用量与账单（约一半已付，一半未结或仅有用量）
                qty_11 = rng.randint(1000, PLANS[plan_code]["included_quota"] // 2)
                conn.execute(
                    "INSERT INTO usage_summaries (tenant_id, period_key, plan_code, total_quantity, updated_at) VALUES (?, '2026-11', ?, ?, '2026-11-13T12:00:00Z')",
                    (tid, plan_code, qty_11),
                )
                if i % 3 == 0 or tid in ("t_cust_012", "t_cust_015"):
                    base_11 = PLANS[plan_code]["monthly_fee_cents"]
                    tx_11 = compute_tax_breakdown(base_11, tax_code)
                    tot_11 = tx_11["gross_total_cents"]
                    inv_11_id = f"INV-202611-{i:04d}"
                    is_paid = (i % 6 == 0 or tid in ("t_cust_012", "t_cust_015"))
                    if is_paid:
                        if cash_bal < tot_11 + 20000:
                            cash_bal += 200000
                            conn.execute(
                                "INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES (?, 'TOPUP', 200000, 0, ?, '11月预存充值', '2026-11-01T08:00:00Z')",
                                (tid, f"top11_{i:03d}"),
                            )
                        cash_bal -= tot_11
                        conn.execute(
                            """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
                               base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
                               currency_unit, status, dispute_reason, created_at, updated_at)
                               VALUES (?, ?, '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z', ?, ?, 0, ?, 0, ?, ?, 0, 'CENTS', 'PAID', '', '2026-11-02T00:00:00Z', '2026-11-02T00:10:00Z')""",
                            (inv_11_id, tid, plan_code, base_11, tx_11["tax_added_cents"], tot_11, tot_11),
                        )
                        conn.execute(
                            "INSERT INTO invoice_payments (id, invoice_id, tenant_id, idempotency_key, cash_paid_cents, promo_paid_cents, total_paid_cents, created_at) VALUES (?, ?, ?, ?, ?, 0, ?, '2026-11-02T00:10:00Z')",
                            (f"pay_11_{i:03d}", inv_11_id, tid, f"auto:{inv_11_id}", tot_11, tot_11),
                        )
                        conn.execute(
                            "INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES (?, 'INVOICE_PAY', ?, 0, ?, ?, '2026-11-02T00:10:00Z')",
                            (tid, -tot_11, inv_11_id, f"支付账单 {inv_11_id}"),
                        )
                    else:
                        conn.execute(
                            """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
                               base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
                               currency_unit, status, dispute_reason, created_at, updated_at)
                               VALUES (?, ?, '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z', ?, ?, 0, ?, 0, ?, 0, 0, 'CENTS', 'OPEN', '', '2026-11-05T00:00:00Z', '2026-11-05T00:00:00Z')""",
                            (inv_11_id, tid, plan_code, base_11, tx_11["tax_added_cents"], tot_11),
                        )

                conn.execute(
                    "INSERT INTO wallets (tenant_id, cash_balance_cents, promo_balance_cents, updated_at) VALUES (?, ?, ?, '2026-11-13T00:00:00Z')",
                    (tid, cash_bal, promo_bal),
                )

        # ------------------------------------------------------------------
        # 3. 埋入 7 个未结清 OPEN 账期受灾现场（编号与普通租户完全一致，无特殊前缀）
        # ------------------------------------------------------------------

        # 受灾点 1: t_cust_019 (云图数据) — ENTERPRISE(80k) 降级 STARTER(5k)，被错算 135000 超额费
        conn.execute("INSERT INTO wallets (tenant_id, cash_balance_cents, promo_balance_cents, updated_at) VALUES ('t_cust_019', 200000, 0, '2026-11-10T10:00:00Z')")
        conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES ('t_cust_019', 'TOPUP', 200000, 0, 'top_019', '公户充值', '2026-11-01T09:00:00Z')")
        conn.execute("INSERT INTO plan_change_history (subscription_id, tenant_id, old_plan_code, new_plan_code, effective_at, proration_cents, reason) VALUES ('sub_cust_019', 't_cust_019', 'ENTERPRISE', 'STARTER', '2026-11-10T10:00:00Z', 0, 'cost_saving')")
        conn.execute("INSERT INTO usage_summaries (tenant_id, period_key, plan_code, total_quantity, updated_at) VALUES ('t_cust_019', '2026-11', 'ENTERPRISE', 80000, '2026-11-10T09:59:00Z')")
        conn.execute("INSERT INTO usage_summaries (tenant_id, period_key, plan_code, total_quantity, updated_at) VALUES ('t_cust_019', '2026-11', 'STARTER', 5000, '2026-11-12T12:00:00Z')")
        conn.execute(
            """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
               base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
               currency_unit, status, dispute_reason, created_at, updated_at)
               VALUES ('INV-202611-0019', 't_cust_019', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z',
               'STARTER', 19900, 135000, 0, 0, 154900, 0, 0, 'CENTS', 'OPEN', '', '2026-11-12T12:30:00Z', '2026-11-12T12:30:00Z')"""
        )

        # 受灾点 2: t_cust_083 (瀚海物联) — PRO(42k，未超5万) 降级 STARTER(15k，真超5k=15000分)，却被合算57k按STARTER收了104000分超额！
        conn.execute("INSERT INTO wallets (tenant_id, cash_balance_cents, promo_balance_cents, updated_at) VALUES ('t_cust_083', 150000, 0, '2026-11-08T14:00:00Z')")
        conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES ('t_cust_083', 'TOPUP', 150000, 0, 'top_083', '公户充值', '2026-11-01T09:30:00Z')")
        conn.execute("INSERT INTO plan_change_history (subscription_id, tenant_id, old_plan_code, new_plan_code, effective_at, proration_cents, reason) VALUES ('sub_cust_083', 't_cust_083', 'PRO', 'STARTER', '2026-11-08T14:00:00Z', 0, 'seasonal_adjust')")
        conn.execute("INSERT INTO usage_summaries (tenant_id, period_key, plan_code, total_quantity, updated_at) VALUES ('t_cust_083', '2026-11', 'PRO', 42000, '2026-11-08T13:59:00Z')")
        conn.execute("INSERT INTO usage_summaries (tenant_id, period_key, plan_code, total_quantity, updated_at) VALUES ('t_cust_083', '2026-11', 'STARTER', 15000, '2026-11-12T18:00:00Z')")
        conn.execute(
            """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
               base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
               currency_unit, status, dispute_reason, created_at, updated_at)
               VALUES ('INV-202611-0083', 't_cust_083', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z',
               'STARTER', 19900, 104000, 0, 0, 123900, 0, 0, 'CENTS', 'OPEN', '', '2026-11-12T18:30:00Z', '2026-11-12T18:30:00Z')"""
        )

        # 受灾点 3: t_cust_034 (蓝海智造) — 钱包已扣款 59900 并落支付记录，但账单卡死在 PENDING_SETTLE (paid_cents=0)
        conn.execute("INSERT INTO wallets (tenant_id, cash_balance_cents, promo_balance_cents, updated_at) VALUES ('t_cust_034', 40100, 0, '2026-11-11T00:05:00Z')")
        conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES ('t_cust_034', 'TOPUP', 100000, 0, 'top_034', '现金充值', '2026-11-01T08:00:00Z')")
        conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES ('t_cust_034', 'INVOICE_PAY', -59900, 0, 'INV-202611-0034', '支付账单 INV-202611-0034', '2026-11-11T00:05:00Z')")
        conn.execute(
            """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
               base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
               currency_unit, status, dispute_reason, created_at, updated_at)
               VALUES ('INV-202611-0034', 't_cust_034', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z',
               'PRO', 59900, 0, 0, 0, 59900, 0, 0, 'CENTS', 'PENDING_SETTLE', '', '2026-11-11T00:05:00Z', '2026-11-11T00:05:00Z')"""
        )
        conn.execute(
            "INSERT INTO invoice_payments (id, invoice_id, tenant_id, idempotency_key, cash_paid_cents, promo_paid_cents, total_paid_cents, created_at) VALUES ('pay_11_034', 'INV-202611-0034', 't_cust_034', 'auto:INV-202611-0034', 59900, 0, 59900, '2026-11-11T00:05:00Z')"
        )

        # 受灾点 4: t_cust_092 (千帆供应链) — 余额仅 12000 不足扣 59900，未扣款但账单永久卡死在 PENDING_SETTLE（应回退为 OPEN）
        conn.execute("INSERT INTO wallets (tenant_id, cash_balance_cents, promo_balance_cents, updated_at) VALUES ('t_cust_092', 12000, 0, '2026-11-01T08:00:00Z')")
        conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES ('t_cust_092', 'TOPUP', 12000, 0, 'top_092', '初始充值', '2026-11-01T08:00:00Z')")
        conn.execute(
            """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
               base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
               currency_unit, status, dispute_reason, created_at, updated_at)
               VALUES ('INV-202611-0092', 't_cust_092', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z',
               'PRO', 59900, 0, 0, 0, 59900, 0, 0, 'CENTS', 'PENDING_SETTLE', '', '2026-11-12T00:05:00Z', '2026-11-12T00:05:00Z')"""
        )

        # 受灾点 5: t_cust_051 (飞跃零售) — 充10000现金+20000赠金，付19900全扣赠金，退10000被误退成现金 -> cash=20000, promo=100
        conn.execute("INSERT INTO wallets (tenant_id, cash_balance_cents, promo_balance_cents, updated_at) VALUES ('t_cust_051', 20000, 100, '2026-11-12T09:00:00Z')")
        conn.execute("INSERT INTO promo_grants (id, tenant_id, initial_cents, remaining_cents, status, expires_at, campaign_code, created_at) VALUES ('pg_cust_051', 't_cust_051', 20000, 100, 'ACTIVE', '2026-12-31T23:59:59Z', 'Q4_PROMO', '2026-11-01T08:05:00Z')")
        conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES ('t_cust_051', 'TOPUP', 10000, 0, 'top_051', '现金充值', '2026-11-01T08:00:00Z')")
        conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES ('t_cust_051', 'PROMO_GRANT', 0, 20000, 'pg_cust_051', '运营赠送金', '2026-11-01T08:05:00Z')")
        conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES ('t_cust_051', 'INVOICE_PAY', 0, -19900, 'INV-202611-0051', '支付账单 INV-202611-0051', '2026-11-02T10:00:00Z')")
        conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES ('t_cust_051', 'REFUND', 10000, 0, 'INV-202611-0051', '账单部分退款', '2026-11-12T09:00:00Z')")
        conn.execute(
            """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
               base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
               currency_unit, status, dispute_reason, created_at, updated_at)
               VALUES ('INV-202611-0051', 't_cust_051', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z',
               'STARTER', 19900, 0, 0, 0, 19900, 19900, 10000, 'CENTS', 'PAID', '', '2026-11-02T10:00:00Z', '2026-11-12T09:00:00Z')"""
        )
        conn.execute(
            "INSERT INTO invoice_payments (id, invoice_id, tenant_id, idempotency_key, cash_paid_cents, promo_paid_cents, total_paid_cents, created_at) VALUES ('pay_11_051', 'INV-202611-0051', 't_cust_051', 'ui:INV-202611-0051', 0, 19900, 19900, '2026-11-02T10:00:00Z')"
        )

        # 受灾点 6: t_cust_067 (锐捷医疗) — 过期赠送金被重复扣减成 -16000
        conn.execute("INSERT INTO wallets (tenant_id, cash_balance_cents, promo_balance_cents, updated_at) VALUES ('t_cust_067', 30000, -16000, '2026-11-12T00:01:00Z')")
        conn.execute("INSERT INTO promo_grants (id, tenant_id, initial_cents, remaining_cents, status, expires_at, campaign_code, created_at) VALUES ('pg_cust_067', 't_cust_067', 10000, 0, 'EXPIRED', '2026-11-01T00:00:00Z', 'OCT_GRANT', '2026-10-01T00:00:00Z')")
        conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES ('t_cust_067', 'TOPUP', 43900, 0, 'top_067', '现金充值', '2026-10-01T08:00:00Z')")
        conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES ('t_cust_067', 'PROMO_GRANT', 0, 10000, 'pg_cust_067', '十月赠送金', '2026-10-01T08:05:00Z')")
        conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES ('t_cust_067', 'INVOICE_PAY', -13900, -6000, 'INV-202610-0067', '支付十月账单', '2026-10-28T10:00:00Z')")
        conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES ('t_cust_067', 'PROMO_EXPIRE', 0, -10000, 'pg_cust_067', '赠送金到期清零', '2026-11-02T00:01:00Z')")
        conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES ('t_cust_067', 'PROMO_EXPIRE', 0, -10000, 'pg_cust_067', '赠送金到期清零', '2026-11-12T00:01:00Z')")
        conn.execute(
            """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
               base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
               currency_unit, status, dispute_reason, created_at, updated_at)
               VALUES ('INV-202610-0067', 't_cust_067', '2026-10', '2026-10-01T00:00:00Z', '2026-10-30T23:59:59Z',
               'STARTER', 19900, 0, 0, 0, 19900, 19900, 0, 'CENTS', 'PAID', '', '2026-10-28T09:00:00Z', '2026-10-28T10:00:00Z')"""
        )

        # 受灾点 7: t_cust_078 (星河传媒) — 零点并发重复生成同周期两张 OPEN 账单
        conn.execute("INSERT INTO wallets (tenant_id, cash_balance_cents, promo_balance_cents, updated_at) VALUES ('t_cust_078', 60000, 0, '2026-11-01T08:00:00Z')")
        conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES ('t_cust_078', 'TOPUP', 60000, 0, 'top_078', '现金充值', '2026-11-01T08:00:00Z')")
        conn.execute(
            """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
               base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
               currency_unit, status, dispute_reason, created_at, updated_at)
               VALUES ('INV-202611-0078', 't_cust_078', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z',
               'STARTER', 19900, 0, 0, 0, 19900, 0, 0, 'CENTS', 'OPEN', '', '2026-11-11T00:00:01Z', '2026-11-11T00:00:01Z')"""
        )
        conn.execute(
            """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
               base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
               currency_unit, status, dispute_reason, created_at, updated_at)
               VALUES ('INV-202611-0978', 't_cust_078', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z',
               'STARTER', 19900, 0, 0, 0, 19900, 0, 0, 'CENTS', 'OPEN', '', '2026-11-11T00:00:02Z', '2026-11-11T00:00:02Z')"""
        )

        # ------------------------------------------------------------------
        # 4. 计算精确的 2026-09 与 2026-10 封账总额，生成 GL 分录与渠道返佣
        # ------------------------------------------------------------------
        rows_09 = conn.execute("SELECT * FROM invoices WHERE period_key = '2026-09' AND status != 'VOID'").fetchall()
        arch_09 = sum(parse_legacy_amount_cents(dict(r), "total_cents") for r in rows_09)

        rows_10 = conn.execute("SELECT * FROM invoices WHERE period_key = '2026-10' AND status != 'VOID'").fetchall()
        arch_10 = sum(parse_legacy_amount_cents(dict(r), "total_cents") for r in rows_10)

        conn.executemany(
            "INSERT INTO accounting_periods (period_key, status, closed_at, closed_by, archived_total_cents) VALUES (?, ?, ?, ?, ?)",
            [
                ("2026-09", "CLOSED", "2026-10-02T02:00:00Z", "finance_director", arch_09),
                ("2026-10", "CLOSED", "2026-11-02T02:00:00Z", "finance_director", arch_10),
                ("2026-11", "OPEN", None, None, None),
            ],
        )

        generate_gl_entries_for_period(conn, "2026-09")
        generate_gl_entries_for_period(conn, "2026-10")
        calculate_period_partner_commissions(conn, "2026-10")
        calculate_period_partner_commissions(conn, "2026-11")

        # 写入几十条正常缓冲事件（已刷盘历史记录）增加真实度
        for e_idx in range(1, 320):
            t_pick = f"t_cust_{(e_idx % 100) + 1:03d}"
            if t_pick in ("t_cust_019", "t_cust_083"):
                continue
            conn.execute(
                """INSERT INTO usage_events (id, tenant_id, metric_code, quantity, plan_code_at_event, occurred_at, period_key, flushed)
                   VALUES (?, ?, 'API_CALLS', ?, NULL, ?, '2026-11', 1)""",
                (f"ue_hist_{e_idx:04d}", t_pick, (e_idx * 37) % 900 + 50, f"2026-11-{(e_idx % 12) + 1:02d}T10:{e_idx % 60:02d}:00Z"),
            )

        # ------------------------------------------------------------------
        # 5. 写入周边企业级业务表记录（数电发票、催收台账、银行水单、审批流、SLA 赔付）
        # ------------------------------------------------------------------
        paid_sample = conn.execute(
            "SELECT id, tenant_id, total_cents, tax_cents FROM invoices WHERE status = 'PAID' AND currency_unit = 'CENTS' ORDER BY id ASC LIMIT 18"
        ).fetchall()
        for f_idx, p_inv in enumerate(paid_sample, start=1):
            gross_c = int(p_inv["total_cents"] or 0)
            tax_c = int(p_inv["tax_cents"] or 0) or int(round((gross_c * 600.0) / 10600.0))
            net_c = max(0, gross_c - tax_c)
            conn.execute(
                """INSERT INTO fapiao_requests (id, tenant_id, invoice_id, fapiao_type, buyer_tax_id, title,
                   net_amount_cents, tax_amount_cents, gross_amount_cents, sheet_count, status, red_letter_of, created_at)
                   VALUES (?, ?, ?, 'VAT_SPECIAL_E', ?, ?, ?, ?, ?, 1, 'ISSUED', NULL, '2026-11-05T11:00:00Z')""",
                (f"fp_2026_{f_idx:04d}", p_inv["tenant_id"], p_inv["id"], f"91310115MA1K3{f_idx:04d}X", f"企业抬头_{p_inv['tenant_id']}", net_c, tax_c, gross_c),
            )

        for b_idx in range(1, 15):
            matched_tid = f"t_cust_{b_idx:03d}" if b_idx <= 12 else None
            st_code = "MATCHED" if matched_tid else "UNMATCHED"
            conn.execute(
                """INSERT INTO bank_statement_imports (id, bank_serial_no, payer_company_name, amount_cents, tx_date,
                   matched_tenant_id, match_confidence_bps, status, created_at)
                   VALUES (?, ?, ?, ?, '2026-11-06', ?, ?, ?, '2026-11-06T17:30:00Z')""",
                (f"bsi_{b_idx:04d}", f"CMB2026110699{b_idx:03d}", f"汇款单位_{b_idx:02d}", 59900 * (1 + (b_idx % 3)), matched_tid, 10000 if matched_tid else 0, st_code),
            )

        conn.executemany(
            """INSERT INTO approval_tickets (id, ticket_type, tenant_id, ref_object_id, amount_cents, requested_by,
               first_approver, second_approver, required_approvals, status, reason, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '2026-11-08T09:00:00Z', '2026-11-08T14:00:00Z')""",
            [
                ("apv_2026_0001", "CONTRACT_DISCOUNT", "t_cust_004", "ctr_004", 220000, "ka_sales_01", "fin_mgr", None, 1, "APPROVED", "年度保底协议例行备案"),
                ("apv_2026_0002", "LARGE_REFUND_CHECK", "t_cust_020", "INV-202610-0020", 650000, "cs_lead", "fin_mgr", "cfo_dir", 2, "APPROVED", "双签复核归档样例"),
            ],
        )

        conn.executemany(
            """INSERT INTO sla_credit_claims (id, tenant_id, period_key, observed_uptime_bps, promised_uptime_bps, credit_cents, status, created_at)
               VALUES (?, ?, '2026-10', ?, 9990, ?, ?, '2026-11-03T10:00:00Z')""",
            [
                ("sla_202610_01", "t_cust_005", 9998, 0, "MEETS_SLA"),
                ("sla_202610_02", "t_cust_015", 9996, 0, "MEETS_SLA"),
            ],
        )

        t_cnt = conn.execute("SELECT COUNT(*) FROM tenants").fetchone()[0]
        i_cnt = conn.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
        l_cnt = conn.execute("SELECT COUNT(*) FROM wallet_ledger").fetchone()[0]
        conn.commit()
        return {
            "tenants": t_cnt,
            "invoices": i_cnt,
            "ledger_rows": l_cnt,
            "archived_2026_09": arch_09,
            "archived_2026_10": arch_10,
        }
    finally:
        conn.close()


def build_logs() -> int:
    rng = random.Random(20261114)
    logs_dir = TEMPLATE_DIR / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    days = [
        ("2026-11-11", "prod_20261111.log", {
            "00:00:02": [
                "2026-11-11 00:00:01 [INFO] yunce.jobs.scheduler: batch trigger as_of=2026-11-11T00:00:00Z",
                "2026-11-11 00:00:01 [INFO] yunce.jobs.settlement: generated cycle invoice INV-202611-0078 tenant=t_cust_078 cycle=2026-11-01T00:00:00Z..2026-12-01T00:00:00Z",
                "2026-11-11 00:00:02 [INFO] yunce.facades.portal: renew_subscription_immediately tenant=t_cust_078 trace=trc_991a",
                "2026-11-11 00:00:02 [INFO] yunce.routes.subscriptions: POST /api/subscriptions/renew tenant=t_cust_078 created INV-202611-0978 cycle=2026-11-01T00:00:00Z..2026-12-01T00:00:00Z",
            ],
            "00:05:01": [
                "2026-11-11 00:05:00 [INFO] yunce.jobs.settlement: auto-settling inv=INV-202611-0034 tenant=t_cust_034",
                "2026-11-11 00:05:01 [ERROR] yunce.jobs.settlement: settlement_job: error on inv=INV-202611-0034 err=transient lock timeout after ledger write",
            ],
            "10:12:04": [
                "2026-11-11 10:12:04 [INFO] yunce.hooks.lifecycle: topic=subscription.plan_changed evicted contract_cache & v1_dead_quota_slab tenant=t_cust_019",
                "2026-11-11 10:12:05 [DEBUG] yunce.compat.quota_cache_shim: tenant_plan_cache hit tenant=t_cust_019 cached_plan=ENTERPRISE ttl_rem=241s",
            ],
            "14:22:10": [
                "2026-11-11 14:22:10 [WARN] yunce.webhook: delivery timeout url=https://hooks.customer-025.example.com/billing attempt=1 (retrying in 60s)",
                "2026-11-11 14:23:11 [INFO] yunce.webhook: delivery succeeded url=https://hooks.customer-025.example.com/billing attempt=2 status=200",
            ],
        }),
        ("2026-11-12", "prod_20261112.log", {
            "00:01:00": [
                "2026-11-12 00:01:00 [INFO] yunce.ledger: expire_promo_grants cutoff=2026-11-12T00:01:00Z grant=pg_cust_067 tenant=t_cust_067 deducted=10000",
                "2026-11-12 00:05:02 [ERROR] yunce.jobs.settlement: settlement_job: error on inv=INV-202611-0092 err=钱包余额不足",
            ],
            "09:00:03": [
                "2026-11-12 09:00:02 [DEBUG] yunce.compat.wallet_bridge: compute_refund_bucket_split inv=INV-202611-0051 legacy_fast_cash_mode=True",
                "2026-11-12 09:00:03 [INFO] yunce.ledger: refund_to_wallet inv=INV-202611-0051 tenant=t_cust_051 refund_cents=10000",
            ],
            "12:30:01": [
                "2026-11-12 12:00:04 [DEBUG] yunce.compat.v1_v2_bridge: resolve_flush_plan_code tenant=t_cust_019 event_plan=None resolved_latest=STARTER",
                "2026-11-12 12:00:05 [INFO] yunce.jobs.metering: metering_flush: tenant=t_cust_019 flushed_qty=5000 target_plan=STARTER",
                "2026-11-12 12:30:01 [INFO] yunce.domain.pricing: calculate_cycle_bill tenant=t_cust_019 period=2026-11 total_qty=85000 plan=STARTER overage_cents=135000",
            ],
            "15:20:33": [
                "2026-11-12 15:20:33 [INFO] yunce.http: GET /api/invoices/INV-202611-0012 caller_tenant=t_cust_044 status=200 3ms",
            ],
            "18:30:02": [
                "2026-11-12 18:00:04 [INFO] yunce.jobs.metering: metering_flush: tenant=t_cust_083 flushed_qty=15000 target_plan=STARTER",
                "2026-11-12 18:30:02 [INFO] yunce.domain.pricing: calculate_cycle_bill tenant=t_cust_083 period=2026-11 total_qty=57000 plan=STARTER overage_cents=104000",
            ],
        }),
        ("2026-11-13", "prod_20261113.log", {
            "10:42:15": [
                "2026-11-13 10:42:15 [INFO] yunce.domain.reconcile: recalculate_invoice_for_period inv=INV-202609-0006 period=2026-09 mode=DIRECT_OVERWRITE",
                "2026-11-13 11:15:20 [INFO] yunce.http: POST /api/admin/jobs/run auth_header=none status=200 51ms",
            ],
            "16:08:44": [
                "2026-11-13 16:08:44 [WARN] yunce.http: slow SQL on /api/admin/gl/2026-10 elapsed=284ms",
                "2026-11-13 17:45:12 [INFO] yunce.jobs.metrics_rollup: snapshot collected active_v1_legacy=15 v3_pipeline_enabled=False",
            ],
        }),
    ]

    endpoints = [
        ("GET", "/health", 200),
        ("GET", "/api/subscriptions/current?period_key=2026-11", 200),
        ("POST", "/api/usage/events", 201),
        ("GET", "/api/usage/summary?period_key=2026-11", 200),
        ("GET", "/api/invoices", 200),
        ("GET", "/api/wallet", 200),
        ("GET", "/api/fapiao", 200),
        ("GET", "/api/partners/commissions?period_key=2026-11", 200),
        ("GET", "/api/admin/analytics/mrr", 200),
        ("GET", "/api/admin/diagnostics/sox-controls", 200),
    ]

    total_lines = 0
    for day_str, fname, anchors in days:
        out_lines = []
        anchor_keys = sorted(anchors.keys())
        ak_idx = 0

        for step in range(1180):
            sec_of_day = int((step / 1180.0) * 86399)
            hh = sec_of_day // 3600
            mm = (sec_of_day % 3600) // 60
            ss = sec_of_day % 60
            hms = f"{hh:02d}:{mm:02d}:{ss:02d}"

            while ak_idx < len(anchor_keys) and anchor_keys[ak_idx] <= hms:
                out_lines.extend(anchors[anchor_keys[ak_idx]])
                ak_idx += 1

            tid_num = rng.randint(1, 113)
            tid = f"t_cust_{tid_num:03d}" if rng.random() > 0.12 else f"t_leg_{rng.randint(1, 15):03d}"
            method, path, code = rng.choice(endpoints)
            ms = rng.randint(1, 19)
            if path == "/api/usage/events":
                q = rng.randint(10, 800)
                out_lines.append(f"{day_str} {hms} [INFO] yunce.http: {method} {path} tenant={tid} qty={q} status={code} {ms}ms")
            elif path == "/health":
                out_lines.append(f"{day_str} {hms} [INFO] yunce.http: GET /health status=200 1ms")
            else:
                out_lines.append(f"{day_str} {hms} [INFO] yunce.http: {method} {path} tenant={tid} status={code} {ms}ms")

        while ak_idx < len(anchor_keys):
            out_lines.extend(anchors[anchor_keys[ak_idx]])
            ak_idx += 1

        (logs_dir / fname).write_text("\n".join(out_lines) + "\n", encoding="utf-8")
        total_lines += len(out_lines)

    # 生成合法导出样例文件
    exp_dir = TEMPLATE_DIR / "data" / "exports"
    exp_dir.mkdir(parents=True, exist_ok=True)
    (exp_dir / "reconcile_2026-10_summary.txt").write_text(
        "period=2026-10\nstatus=CLOSED\nverified_by=finance_director\n",
        encoding="utf-8",
    )
    return total_lines


if __name__ == "__main__":
    db_info = build_database()
    log_cnt = build_logs()
    print(f"DB built: {db_info}")
    print(f"Logs built: {log_cnt} lines")
