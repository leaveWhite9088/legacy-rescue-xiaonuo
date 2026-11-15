#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""黄金补丁分卷三：交付数据库 data/yunce_billing.db 全库不变量审计与平账（A2-01 ~ A2-48）。
严格遵守封账铁律：2026-09 与 2026-10 历史已关账账期零修改，历史差额统一于 2026-11 OPEN 期登记跨期调账单。
"""
from pathlib import Path
import sqlite3
import sys


def repair_database(sandbox_dir: Path) -> None:
    db_path = sandbox_dir / "data" / "yunce_billing.db"
    old_sys_path = list(sys.path)
    sb_str = str(sandbox_dir.resolve())
    sys.path = [sb_str] + [p for p in sys.path if p != sb_str and "legacy_template" not in p]
    for mod_name in list(sys.modules.keys()):
        if mod_name == "app" or mod_name.startswith("app."):
            sys.modules.pop(mod_name, None)

    from app.domain.gl_exporter import generate_gl_entries_for_period
    from app.domain.partner_commission import calculate_period_partner_commissions
    from app.domain.reconcile import recalculate_invoice_for_period
    from app.reporting.asc606_revrec_schedule import persist_multi_month_revrec_schedule

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    now = "2026-11-14T12:00:00Z"

    try:
        with conn:
            # 1. Cat 1 & Cat 2 (A2-01..08): 重算 2026-11 OPEN 期内计量分段、价外税漏提与过期协议误保底账单
            for iid in (
                "INV-202611-0031",
                "INV-202611-0036",
                "INV-202611-0041",
                "INV-202611-0046",
                "INV-202611-0051",
                "INV-202611-0056",
                "INV-202611-0061",
                "INV-202611-0066",
            ):
                recalculate_invoice_for_period(conn, iid, actor="golden_audit")

            # 2. Cat 3 (A2-09..12): 作废 2026-11 并发重复续期账单与已停机租户误出账单
            for tid in ("t_cust_071", "t_cust_076", "t_cust_081"):
                rows = conn.execute(
                    "SELECT id FROM invoices WHERE tenant_id = ? AND period_key = '2026-11' AND status = 'OPEN' ORDER BY id ASC",
                    (tid,),
                ).fetchall()
                for dup in rows[1:]:
                    conn.execute("UPDATE invoices SET status = 'VOID', updated_at = ? WHERE id = ?", (now, dup["id"]))
            conn.execute("UPDATE invoices SET status = 'VOID', updated_at = ? WHERE id = 'INV-202611-0086'", (now,))

            # 3. Cat 4 (A2-13..17): 对账恢复卡死在 PENDING_SETTLE 的账单（支付流水已落账则推进 PAID，未扣款欠费则退回 OPEN 并登记死信）
            pending_rows = conn.execute(
                "SELECT id, tenant_id, total_cents FROM invoices WHERE period_key = '2026-11' AND status = 'PENDING_SETTLE'"
            ).fetchall()
            for prow in pending_rows:
                iid = prow["id"]
                tid = prow["tenant_id"]
                tot_c = int(prow["total_cents"])
                paid_sum = int(
                    conn.execute("SELECT COALESCE(SUM(total_paid_cents), 0) FROM invoice_payments WHERE invoice_id = ?", (iid,)).fetchone()[0]
                )
                if paid_sum >= tot_c and tot_c > 0:
                    conn.execute("UPDATE invoices SET status = 'PAID', paid_cents = ?, updated_at = ? WHERE id = ?", (paid_sum, now, iid))
                else:
                    conn.execute("UPDATE invoices SET status = 'OPEN', paid_cents = ?, updated_at = ? WHERE id = ?", (paid_sum, now, iid))
                    ex_dlq = conn.execute("SELECT id FROM settlement_dlq WHERE invoice_id = ? LIMIT 1", (iid,)).fetchone()
                    if ex_dlq:
                        conn.execute("UPDATE settlement_dlq SET status = 'PENDING', updated_at = ? WHERE id = ?", (now, ex_dlq["id"]))
                    else:
                        conn.execute(
                            "INSERT INTO settlement_dlq (invoice_id, tenant_id, error_msg, retry_count, status, created_at, updated_at) "
                            "VALUES (?, ?, '钱包余额不足', 1, 'PENDING', ?, ?)",
                            (iid, tid, now, now),
                        )

            # 4. Cat 5 (A2-18..21): 冲正死信重试无视首笔部分付款造成的超扣差额，并标记 DLQ 为 RESOLVED
            for d_id in (116, 121, 126, 131):
                tid = f"t_cust_{d_id:03d}"
                iid = f"INV-202611-{d_id:04d}"
                inv = conn.execute("SELECT total_cents, paid_cents FROM invoices WHERE id = ?", (iid,)).fetchone()
                if inv and int(inv["paid_cents"]) > int(inv["total_cents"]):
                    over = int(inv["paid_cents"]) - int(inv["total_cents"])
                    dlq_pay_id = f"pay_11_{d_id}_dlq"
                    conn.execute(
                        "UPDATE invoice_payments SET cash_paid_cents = cash_paid_cents - ?, total_paid_cents = total_paid_cents - ? WHERE id = ?",
                        (over, over, dlq_pay_id),
                    )
                    conn.execute("UPDATE invoices SET paid_cents = ?, updated_at = ? WHERE id = ?", (int(inv["total_cents"]), now, iid))
                    conn.execute("UPDATE wallets SET cash_balance_cents = cash_balance_cents + ?, updated_at = ? WHERE tenant_id = ?", (over, now, tid))
                    conn.execute(
                        "INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) "
                        "VALUES (?, 'ADJUSTMENT', ?, 0, ?, '冲正DLQ重复多扣差额', ?)",
                        (tid, over, iid, now),
                    )
                conn.execute("UPDATE settlement_dlq SET status = 'RESOLVED', updated_at = ? WHERE invoice_id = ?", (now, iid))

            # 5. Cat 6 (A2-22..27): 订正赠金洗现退款、过期重复扣成负数的赠金池及预览误锁券批次
            # A2-22: t_cust_136 退回的 10000 分应归入赠送金而非现金
            conn.execute("UPDATE wallets SET cash_balance_cents = 10000, promo_balance_cents = 10100, updated_at = ? WHERE tenant_id = 't_cust_136'", (now,))
            conn.execute("UPDATE promo_grants SET remaining_cents = 10100, status = 'ACTIVE' WHERE id = 'pg_cust_136'")
            conn.execute("UPDATE wallet_ledger SET cash_delta_cents = 0, promo_delta_cents = 10000 WHERE tenant_id = 't_cust_136' AND entry_type = 'REFUND' AND ref_id = 'INV-202611-0136'")

            # A2-23: t_cust_141 退回 40000 分应拆为 29900 现金 + 10100 赠送金
            conn.execute("UPDATE wallets SET cash_balance_cents = 50000, promo_balance_cents = 10100, updated_at = ? WHERE tenant_id = 't_cust_141'", (now,))
            conn.execute("UPDATE promo_grants SET remaining_cents = 10100, status = 'ACTIVE' WHERE id = 'pg_cust_141'")
            conn.execute("UPDATE wallet_ledger SET cash_delta_cents = 29900, promo_delta_cents = 10100 WHERE tenant_id = 't_cust_141' AND entry_type = 'REFUND' AND ref_id = 'INV-202611-0141'")

            # A2-24: t_cust_146 过期赠金仅剩 4000 分却被重复扣了两次 -10000
            conn.execute("UPDATE wallets SET cash_balance_cents = 30000, promo_balance_cents = 0, updated_at = ? WHERE tenant_id = 't_cust_146'", (now,))
            conn.execute("DELETE FROM wallet_ledger WHERE tenant_id = 't_cust_146' AND entry_type = 'PROMO_EXPIRE'")
            conn.execute(
                "INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) "
                "VALUES ('t_cust_146', 'PROMO_EXPIRE', 0, -4000, 'pg_cust_146', '到期剩余赠金清零', '2026-11-02T00:01:00Z')"
            )

            # A2-25: t_cust_151 旧券剩余 5000 分到期清零，保留有效新券 pg_cust_151_b (8000 分)
            conn.execute("UPDATE wallets SET cash_balance_cents = 50000, promo_balance_cents = 8000, updated_at = ? WHERE tenant_id = 't_cust_151'", (now,))
            conn.execute("DELETE FROM wallet_ledger WHERE tenant_id = 't_cust_151' AND entry_type = 'PROMO_EXPIRE'")
            conn.execute(
                "INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) "
                "VALUES ('t_cust_151', 'PROMO_EXPIRE', 0, -5000, 'pg_cust_151_a', '到期剩余赠金清零', '2026-11-02T00:01:00Z')"
            )

            # A2-26, A2-27: 释放被 GET 预览接口误锁为 LOCKED_PREVIEW 的有效赠金批次
            conn.execute("UPDATE promo_grants SET status = 'ACTIVE' WHERE status = 'LOCKED_PREVIEW'")

            # 6. Cat 7 (A2-28..31): 修复跨期调账正负号反算与重复冲减错单
            for a_id in (166, 171, 176, 181):
                iid = f"INV-202611-{a_id:04d}"
                inv = conn.execute("SELECT base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents FROM invoices WHERE id = ?", (iid,)).fetchone()
                adj = conn.execute("SELECT delta_cents FROM billing_adjustments WHERE id = ?", (f"adj_202611_{a_id:04d}",)).fetchone()
                if inv and adj:
                    true_tot = int(inv["base_fee_cents"]) + int(inv["overage_fee_cents"]) + int(inv["tax_cents"]) + int(inv["late_fee_cents"]) + int(adj["delta_cents"])
                    conn.execute("UPDATE invoices SET total_cents = ?, updated_at = ? WHERE id = ?", (true_tot, now, iid))

            # 7. Cat 8 (A2-32..35): 重新按出账日锁汇汇率折算外币账单 + 补齐保证金划扣实付核销记录
            conn.execute("UPDATE invoices SET total_cents = 215550, updated_at = ? WHERE id = 'INV-202611-0185'", (now,))
            conn.execute("UPDATE fx_settlement_logs SET applied_rate_bps = 71850, settled_cny_cents = 215550 WHERE id = 'fxs_185'")
            conn.execute("UPDATE invoices SET total_cents = 107200, updated_at = ? WHERE id = 'INV-202611-0188'", (now,))
            conn.execute("UPDATE fx_settlement_logs SET applied_rate_bps = 53600, settled_cny_cents = 107200 WHERE id = 'fxs_188'")

            for esc_id, applied_amt, new_st in ((191, 59900, "PAID"), (193, 80000, "OPEN")):
                tid = f"t_cust_{esc_id:03d}"
                iid = f"INV-202611-{esc_id:04d}"
                conn.execute("UPDATE invoices SET paid_cents = ?, status = ?, updated_at = ? WHERE id = ?", (applied_amt, new_st, now, iid))
                conn.execute(
                    "INSERT OR REPLACE INTO invoice_payments (id, invoice_id, tenant_id, idempotency_key, cash_paid_cents, promo_paid_cents, total_paid_cents, created_at) "
                    "VALUES (?, ?, ?, ?, ?, 0, ?, '2026-11-12T15:00:00Z')",
                    (f"pay_esc_{esc_id}", iid, tid, f"escrow:{iid}", applied_amt, applied_amt),
                )

            # 8. Cat 9 (A2-36..39): 冲正复利多计提滞纳金、解封争议冻结误停机及已缴清欠费租户
            conn.execute("UPDATE invoices SET late_fee_cents = 2995, total_cents = 62895, updated_at = ? WHERE id = 'INV-202611-0196'", (now,))
            conn.execute("UPDATE dunning_cases SET unpaid_cents = 62895, updated_at = ? WHERE id = 'dun_196'", (now,))

            conn.execute("UPDATE invoices SET late_fee_cents = 5000, total_cents = 204900, updated_at = ? WHERE id = 'INV-202611-0199'", (now,))
            conn.execute("UPDATE dunning_cases SET unpaid_cents = 105000, updated_at = ? WHERE id = 'dun_199'", (now,))

            conn.execute("UPDATE invoices SET late_fee_cents = 0, total_cents = 59900, updated_at = ? WHERE id = 'INV-202611-0202'", (now,))
            conn.execute("UPDATE dunning_cases SET status = 'RESOLVED', unpaid_cents = 0, updated_at = ? WHERE id = 'dun_202'", (now,))
            conn.execute("UPDATE tenants SET status = 'ACTIVE' WHERE id IN ('t_cust_202', 't_cust_205')")
            conn.execute("UPDATE subscriptions SET status = 'ACTIVE', updated_at = ? WHERE tenant_id IN ('t_cust_202', 't_cust_205')", (now,))

            # 9. Cat 10 (A2-40..44): 订正红字正数数电票与原蓝票状态、作废并发重复蓝票、冲销二次重复认领水单
            for rf_id, net_c, tax_c, gross_c in ((208, -56509, -3391, -59900), (210, -188585, -11315, -199900)):
                conn.execute(
                    "UPDATE fapiao_requests SET net_amount_cents = ?, tax_amount_cents = ?, gross_amount_cents = ? WHERE id = ?",
                    (net_c, tax_c, gross_c, f"FP-RED-{rf_id:04d}"),
                )
                conn.execute("UPDATE fapiao_requests SET status = 'RED_REVERSED' WHERE id = ?", (f"FP-202611-{rf_id:04d}",))

            conn.execute("UPDATE fapiao_requests SET status = 'VOID' WHERE id = 'FP-202611-0212B'")

            for bs_id, serial_no, amt_c in ((214, "CMB2026110800214", 59900), (216, "ICBC2026110900216", 199900)):
                tid = f"t_cust_{bs_id:03d}"
                conn.execute("UPDATE wallets SET cash_balance_cents = ?, updated_at = ? WHERE tenant_id = ?", (amt_c, now, tid))
                conn.execute(
                    "DELETE FROM wallet_ledger WHERE tenant_id = ? AND ref_id = ? AND note LIKE '人工水单认领:%'",
                    (tid, serial_no),
                )

            # 10. A2-48: 对 2026-09 与 2026-10 已封账历史差额账单严禁改原单，在 2026-11 OPEN 期登记跨期调账单
            recalculate_invoice_for_period(conn, "INV-202609-0012", actor="golden_audit")
            recalculate_invoice_for_period(conn, "INV-202610-0024", actor="golden_audit")

            # 11. Subledgers (A2-45..47): 重算 2026-11 递延摊销表、渠道返佣清分表与复式总账凭证（绝不触碰 2026-09/10）
            persist_multi_month_revrec_schedule(conn, "INV-202611-0219", 3)
            persist_multi_month_revrec_schedule(conn, "INV-202611-0220", 3)
            calculate_period_partner_commissions(conn, "2026-11")
            generate_gl_entries_for_period(conn, "2026-11")
    finally:
        conn.close()
        sys.path = old_sys_path
