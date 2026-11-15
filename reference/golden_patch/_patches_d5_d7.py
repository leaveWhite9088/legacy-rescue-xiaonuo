#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""黄金补丁分卷二：业务域 5 ~ 业务域 7 及多视图前端修复（BUG-32 ~ BUG-60）。"""
from pathlib import Path
from _patches_d1_d4 import replace_exact


def apply_d5_gl_revrec(base: Path) -> None:
    # BUG-32: 复式总账处理调账差额（gross vs 分项合计），保持借贷平衡与净应收 1122 精确一致
    replace_exact(
        base,
        "app/domain/gl_exporter.py",
        """        legs = [
            ("6001-SaaSBaseRevenue", base_rev),
            ("6002-UsageOverageRevenue", overage),
            ("6301-LateFeeIncome", late),
            ("2221-TaxPayable", tax),
        ]
        for credit_acct, amt in legs:""",
        """        comp_sum = base_rev + overage + late + tax
        adj_diff = gross - comp_sum
        if adj_diff < 0:
            disc = abs(adj_diff)
            conn.execute(
                "INSERT INTO gl_journal_entries (period_key, ref_type, ref_id, debit_account, credit_account, amount_cents, debit_cents, credit_cents, created_at) "
                "VALUES (?, 'INVOICE', ?, '6009-BillingAdjustmentContra', '', ?, ?, 0, ?)",
                (period_key, d["id"], disc, disc, now),
            )
            total_debit += disc
            entries.append({"ref_id": d["id"], "debit": "6009-BillingAdjustmentContra", "credit": "", "amount_cents": disc, "debit_cents": disc, "credit_cents": 0})
        legs = [
            ("6001-SaaSBaseRevenue", base_rev),
            ("6002-UsageOverageRevenue", overage),
            ("6301-LateFeeIncome", late),
            ("2221-TaxPayable", tax),
        ]
        if adj_diff > 0:
            legs.append(("6003-BillingAdjustmentRevenue", adj_diff))
        for credit_acct, amt in legs:""",
    )

    # BUG-33: ERP 同步钩子订阅 invoice.refunded 且仅按实退现金生成负数冲销凭证
    replace_exact(
        base,
        "app/hooks/erp_sync_hooks.py",
        """        _pending_voucher_refs.append({
            "kind": "REFUND_REVERSAL",
            "invoice_id": payload.get("invoice_id"),
            "tenant_id": payload.get("tenant_id"),
            "amount_cents": abs(int(payload.get("refund_cents", 0))),
        })""",
        """        cash_ref = int(payload.get("cash_refunded_cents", 0))
        _pending_voucher_refs.append({
            "kind": "REFUND_REVERSAL",
            "invoice_id": payload.get("invoice_id"),
            "tenant_id": payload.get("tenant_id"),
            "amount_cents": -abs(cash_ref) if cash_ref > 0 else 0,
        })""",
    )
    replace_exact(
        base,
        "app/hooks/erp_sync_hooks.py",
        """def register_erp_sync_hooks() -> None:
    event_bus.subscribe("invoice.paid", on_invoice_paid_for_erp)""",
        """def register_erp_sync_hooks() -> None:
    event_bus.subscribe("invoice.paid", on_invoice_paid_for_erp)
    event_bus.subscribe("invoice.refunded", on_invoice_refunded_for_erp)""",
    )

    # BUG-34: ASC 606 多月递延摊销先做价税分离，再按 allocate_pro_rata_cents 吸收尾差确保末期清零
    replace_exact(
        base,
        "app/reporting/asc606_revrec_schedule.py",
        """    revenue_pool = gross_total
    monthly_share = revenue_pool // months

    conn.execute("DELETE FROM deferred_revenue_schedules WHERE invoice_id = ?", (invoice_id,))
    now = utc_now_iso()
    rem = revenue_pool
    items: List[Dict[str, Any]] = []
    for idx in range(months):
        p_key = _advance_month_key(str(inv["period_key"]), idx)
        rec_amt = monthly_share""",
        """    tax_code = str(inv.get("tax_profile_code") or "CN_VAT_6_INCLUSIVE")
    tp = TAX_PROFILES.get(tax_code, TAX_PROFILES["CN_VAT_6_INCLUSIVE"])
    if tp["inclusive"]:
        revenue_pool = _strip_inclusive_vat(gross_total, tax_code)
    else:
        revenue_pool = max(0, gross_total - int(inv.get("tax_cents") or 0))
    shares = allocate_pro_rata_cents(revenue_pool, [1] * months)

    conn.execute("DELETE FROM deferred_revenue_schedules WHERE invoice_id = ?", (invoice_id,))
    now = utc_now_iso()
    rem = revenue_pool
    items: List[Dict[str, Any]] = []
    for idx in range(months):
        p_key = _advance_month_key(str(inv["period_key"]), idx)
        rec_amt = shares[idx]""",
    )

    # BUG-35: 期中升配变更冻结已确认/早于变更账期的历史行，未来适用法分摊剩余及新增净额
    replace_exact(
        base,
        "app/revenue_accounting_ifrs15/contract_modification_accounting.py",
        """    total_pool = sum(int(r["recognized_cents"]) for r in rows) + int(added_net_cents)
    n_all = len(rows)
    base_share = total_pool // n_all
    rem = total_pool
    updated_rows = []
    for idx, r in enumerate(rows):
        share = base_share if idx < n_all - 1 else (total_pool - base_share * (n_all - 1))
        rem = max(0, rem - share)
        conn.execute(
            "UPDATE deferred_revenue_schedules SET recognized_cents = ?, deferred_closing_cents = ?, updated_at = ? WHERE id = ?",
            (share, rem, now, r["id"]),
        )
        updated_rows.append({
            "id": r["id"],
            "period_key": r["period_key"],
            "status": r["status"],
            "recognized_cents": share,
            "deferred_closing_cents": rem,
        })""",
        """    frozen_rows = [r for r in rows if r["status"] == "RECOGNIZED" or str(r["period_key"]) < modification_period_key]
    open_rows = [r for r in rows if not (r["status"] == "RECOGNIZED" or str(r["period_key"]) < modification_period_key)]
    future_pool = sum(int(r["recognized_cents"]) for r in open_rows) + int(added_net_cents)
    n_open = max(1, len(open_rows))
    base_share = future_pool // n_open
    rem_future = future_pool
    updated_rows = []
    for r in frozen_rows:
        updated_rows.append({
            "id": r["id"],
            "period_key": r["period_key"],
            "status": r["status"],
            "recognized_cents": int(r["recognized_cents"]),
            "deferred_closing_cents": int(r["deferred_closing_cents"]),
        })
    for idx, r in enumerate(open_rows):
        share = base_share if idx < n_open - 1 else (future_pool - base_share * (n_open - 1))
        rem_future = max(0, rem_future - share)
        conn.execute(
            "UPDATE deferred_revenue_schedules SET recognized_cents = ?, deferred_closing_cents = ?, updated_at = ? WHERE id = ?",
            (share, rem_future, now, r["id"]),
        )
        updated_rows.append({
            "id": r["id"],
            "period_key": r["period_key"],
            "status": r["status"],
            "recognized_cents": share,
            "deferred_closing_cents": rem_future,
        })""",
    )

    # BUG-36, BUG-37, BUG-38
    replace_exact(
        base,
        "app/finance_recon_hub/promo_liability_rollforward.py",
        "    ledger_ending = grant_in + consumed_out + expired_out + other_net",
        "    ledger_ending = grant_in + consumed_out + refund_restored + expired_out + other_net",
    )
    replace_exact(
        base,
        "app/finance_recon_hub/three_way_cdr_bill_gl.py",
        """    fanout_rows = conn.execute(
        \"\"\"
        SELECT i.*, u.total_quantity AS seg_qty
        FROM invoices i
        LEFT JOIN usage_summaries u ON u.tenant_id = i.tenant_id AND u.period_key = i.period_key
        WHERE i.period_key = ? AND i.status != 'VOID'
        \"\"\",
        (period_key,),
    ).fetchall()""",
        """    fanout_rows = conn.execute(
        \"\"\"
        SELECT i.*, COALESCE(ua.seg_qty, 0) AS seg_qty
        FROM invoices i
        LEFT JOIN (
            SELECT tenant_id, period_key, SUM(total_quantity) AS seg_qty
            FROM usage_summaries
            GROUP BY tenant_id, period_key
        ) ua ON ua.tenant_id = i.tenant_id AND ua.period_key = i.period_key
        WHERE i.period_key = ? AND i.status != 'VOID'
        \"\"\",
        (period_key,),
    ).fetchall()""",
    )
    replace_exact(
        base,
        "app/reporting/tax_filing_vat_return.py",
        "    prc_total_vat = sum(b[\"output_vat_cents\"] for b in buckets.values())",
        "    prc_total_vat = sum(b[\"output_vat_cents\"] for code, b in buckets.items() if TAX_PROFILES[code].get(\"fapiao_eligible\", True))",
    )


def apply_d6_partner_dunning_sod(base: Path) -> None:
    # BUG-39, BUG-40, BUG-41, BUG-42, BUG-43: 渠道返佣与二级分润修复
    replace_exact(
        base,
        "app/domain/partner_commission.py",
        """        t_ids = info["tenants"]
        placeholders = ",".join("?" for _ in t_ids)
        # 统计该期账单现金实收减去现金退款
        pay_row = conn.execute(
            f\"\"\"
            SELECT COALESCE(SUM(p.cash_paid_cents), 0) AS cash_in
            FROM invoice_payments p
            JOIN invoices i ON i.id = p.invoice_id
            WHERE i.period_key = ? AND i.status != 'VOID' AND p.tenant_id IN ({placeholders})
            \"\"\",
            (period_key, *t_ids),
        ).fetchone()
        ref_row = conn.execute(
            f\"\"\"
            SELECT COALESCE(SUM(l.cash_delta_cents), 0) AS cash_refund
            FROM wallet_ledger l
            JOIN invoices i ON i.id = l.ref_id
            WHERE l.entry_type = 'REFUND' AND i.period_key = ? AND l.tenant_id IN ({placeholders})
            \"\"\",
            (period_key, *t_ids),
        ).fetchone()

        net_cash = max(0, int(pay_row["cash_in"]) - int(ref_row["cash_refund"]))
        tier_eval = evaluate_partner_dynamic_tier_from_db(conn, pcode, period_key, base_tier=info["tier"])
        eff_tier = tier_eval["effective_tier"]
        tier_cfg = PARTNER_TIERS.get(eff_tier, PARTNER_TIERS["SILVER"])
        comm_cents = apply_bps(net_cash, tier_cfg["rate_bps"])
        comm_id = f"pc_{period_key.replace('-', '')}_{pcode}"

        conn.execute(
            \"\"\"
            INSERT INTO partner_commissions (id, partner_code, period_key, net_cash_collected_cents, commission_cents, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'CALCULATED', ?)
            ON CONFLICT(partner_code, period_key) DO UPDATE SET
                net_cash_collected_cents = excluded.net_cash_collected_cents,
                commission_cents = excluded.commission_cents,
                status = 'CALCULATED',
                created_at = excluded.created_at
            \"\"\",
            (comm_id, pcode, period_key, net_cash, comm_cents, now),
        )""",
        """        existing_pc = conn.execute(
            "SELECT * FROM partner_commissions WHERE partner_code = ? AND period_key = ?",
            (pcode, period_key),
        ).fetchone()
        if existing_pc and existing_pc["status"] == "PAID_OUT":
            results.append({
                "id": existing_pc["id"],
                "partner_code": pcode,
                "period_key": period_key,
                "tier": info["tier"],
                "net_cash_collected_cents": int(existing_pc["net_cash_collected_cents"]),
                "commission_cents": int(existing_pc["commission_cents"]),
                "status": "PAID_OUT",
            })
            continue

        pay_row = conn.execute(
            \"\"\"
            SELECT COALESCE(SUM(p.cash_paid_cents), 0) AS cash_in
            FROM invoice_payments p
            JOIN invoices i ON i.id = p.invoice_id
            JOIN partner_referrals r ON r.tenant_id = p.tenant_id
            WHERE r.partner_code = ? AND i.period_key = ? AND i.status != 'VOID' AND p.created_at >= r.bound_at
            \"\"\",
            (pcode, period_key),
        ).fetchone()
        ref_row = conn.execute(
            \"\"\"
            SELECT COALESCE(SUM(l.cash_delta_cents), 0) AS cash_refund
            FROM wallet_ledger l
            JOIN invoices i ON i.id = l.ref_id
            JOIN partner_referrals r ON r.tenant_id = l.tenant_id
            WHERE r.partner_code = ? AND l.entry_type = 'REFUND' AND substr(l.created_at, 1, 7) = ? AND l.created_at >= r.bound_at
            \"\"\",
            (pcode, period_key),
        ).fetchone()

        net_cash = int(pay_row["cash_in"]) - int(ref_row["cash_refund"])
        tier_eval = evaluate_partner_dynamic_tier_from_db(conn, pcode, period_key, base_tier=info["tier"])
        eff_tier = tier_eval["effective_tier"]
        tier_cfg = PARTNER_TIERS.get(eff_tier, PARTNER_TIERS["SILVER"])
        comm_cents = -apply_bps(abs(net_cash), tier_cfg["rate_bps"]) if net_cash < 0 else apply_bps(net_cash, tier_cfg["rate_bps"])
        comm_id = f"pc_{period_key.replace('-', '')}_{pcode}"

        conn.execute(
            \"\"\"
            INSERT INTO partner_commissions (id, partner_code, period_key, net_cash_collected_cents, commission_cents, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'CALCULATED', ?)
            ON CONFLICT(partner_code, period_key) DO UPDATE SET
                net_cash_collected_cents = excluded.net_cash_collected_cents,
                commission_cents = excluded.commission_cents,
                status = 'CALCULATED',
                created_at = excluded.created_at
            \"\"\",
            (comm_id, pcode, period_key, net_cash, comm_cents, now),
        )""",
    )
    replace_exact(
        base,
        "app/workflows_legacy_fsm/partner_rebate_tier_fsm.py",
        """    perf_row = conn.execute(
        f\"\"\"
        SELECT COALESCE(SUM(i.total_cents), 0) AS perf_cents
        FROM invoices i
        JOIN partner_referrals r ON r.tenant_id = i.tenant_id
        WHERE r.partner_code = ? AND i.status != 'VOID' AND i.period_key IN ({p_marks})
        \"\"\",
        (partner_code, *q_periods),
    ).fetchone()
    perf_cents = int(perf_row["perf_cents"] or 0) if perf_row else 0""",
        """    pay_row = conn.execute(
        f\"\"\"
        SELECT COALESCE(SUM(p.cash_paid_cents), 0) AS cash_in
        FROM invoice_payments p
        JOIN invoices i ON i.id = p.invoice_id
        JOIN partner_referrals r ON r.tenant_id = p.tenant_id
        WHERE r.partner_code = ? AND i.status != 'VOID' AND i.period_key IN ({p_marks}) AND p.created_at >= r.bound_at
        \"\"\",
        (partner_code, *q_periods),
    ).fetchone()
    ref_row = conn.execute(
        f\"\"\"
        SELECT COALESCE(SUM(l.cash_delta_cents), 0) AS cash_ref
        FROM wallet_ledger l
        JOIN partner_referrals r ON r.tenant_id = l.tenant_id
        WHERE r.partner_code = ? AND l.entry_type = 'REFUND' AND substr(l.created_at, 1, 7) IN ({p_marks}) AND l.created_at >= r.bound_at
        \"\"\",
        (partner_code, *q_periods),
    ).fetchone()
    perf_cents = max(0, int(pay_row["cash_in"] or 0) - int(ref_row["cash_ref"] or 0))""",
    )
    replace_exact(
        base,
        "app/partner_settlement_2024/subagent_split_router.py",
        "        parent_override_comm = apply_bps(net_cash, parent_bps)",
        "        parent_override_comm = apply_bps(net_cash, max(0, parent_bps - child_bps))",
    )

    # BUG-45 & BUG-46: 争议冻结期豁免催收与停机 + 滞纳金按剩余未付本金单次幂等计提
    replace_exact(
        base,
        "app/domain/dunning_engine.py",
        """    for r in rows:
        d = dict(r)
        overdue_days = _calc_overdue_days(str(d["cycle_end"]), as_of_iso)""",
        """    for r in rows:
        d = dict(r)
        frz = conn.execute(
            "SELECT 1 FROM dispute_tickets WHERE invoice_id = ? AND status = 'OPEN' AND freeze_auto_debit = 1 LIMIT 1",
            (d["id"],),
        ).fetchone()
        if frz:
            continue
        overdue_days = _calc_overdue_days(str(d["cycle_end"]), as_of_iso)""",
    )
    replace_exact(
        base,
        "app/jobs/dunning_escalation_job.py",
        """        if get_period_status(conn, inv["period_key"]) == "OPEN" and inv["currency_unit"] == "CENTS":
            fee = compute_late_fee_cents(int(inv["total_cents"]), is_overdue=True)
            if fee > 0:
                conn.execute(
                    "UPDATE invoices SET late_fee_cents = late_fee_cents + ?, total_cents = total_cents + ?, updated_at = ? WHERE id = ?",
                    (fee, fee, as_of_iso, inv_id),
                )
                late_fees_accrued += 1""",
        """        if get_period_status(conn, inv["period_key"]) == "OPEN" and inv["currency_unit"] == "CENTS" and int(inv["late_fee_cents"] or 0) == 0:
            unpaid_principal = max(0, int(inv["total_cents"]) - int(inv["paid_cents"]))
            fee = compute_late_fee_cents(unpaid_principal, is_overdue=True)
            if fee > 0:
                conn.execute(
                    "UPDATE invoices SET late_fee_cents = ?, total_cents = total_cents + ?, updated_at = ? WHERE id = ?",
                    (fee, fee, as_of_iso, inv_id),
                )
                late_fees_accrued += 1""",
    )

    # BUG-47, BUG-48, BUG-49, BUG-50: 审批职责分离归一化、决策白名单、并发锁及大额退款双签拦截
    replace_exact(
        base,
        "app/routes/approvals.py",
        """    try:
        with tx_context(db_path) as conn:
            res = decide_finance_approval(conn, ticket_id, approver=approver, decision=decision)""",
        """    try:
        with tx_context(db_path, immediate=True) as conn:
            res = decide_finance_approval(conn, ticket_id, approver=approver, decision=decision)""",
    )
    replace_exact(
        base,
        "app/services/approval_workflow_service.py",
        """    if t["status"] in ("APPROVED", "REJECTED"):
        raise ValueError(f"审批单已终审结束: {t['status']}")
    if approver == t["requested_by"]:
        raise PermissionError("申请人本人不得审批自己发起的财务工单（职责分离原则）")

    now = _now_iso()
    dec = decision.strip().upper()
    if dec == "REJECT":
        conn.execute(
            "UPDATE approval_tickets SET status = 'REJECTED', updated_at = ? WHERE id = ?",
            (now, ticket_id),
        )
        return get_approval_ticket(conn, ticket_id)  # type: ignore

    if int(t["required_approvals"]) == 1:
        conn.execute(
            "UPDATE approval_tickets SET first_approver = ?, status = 'APPROVED', updated_at = ? WHERE id = ?",
            (approver, now, ticket_id),
        )
    else:
        if not t["first_approver"]:
            conn.execute(
                "UPDATE approval_tickets SET first_approver = ?, status = 'FIRST_APPROVED', updated_at = ? WHERE id = ?",
                (approver, now, ticket_id),
            )
        else:
            if t["first_approver"] == approver:
                raise PermissionError("大额双签工单必须由两名不同财务审批人会签")
            conn.execute(
                "UPDATE approval_tickets SET second_approver = ?, status = 'APPROVED', updated_at = ? WHERE id = ?",
                (approver, now, ticket_id),
            )""",
        """    if t["status"] in ("APPROVED", "REJECTED"):
        raise ValueError(f"审批单已终审结束: {t['status']}")
    norm_actor = (approver or "").strip().lower()
    if not norm_actor:
        raise ValueError("审批人不能为空")
    if norm_actor == str(t["requested_by"] or "").strip().lower():
        raise PermissionError("申请人本人不得审批自己发起的财务工单（职责分离原则）")

    now = _now_iso()
    dec = (decision or "").strip().upper()
    if dec not in ("APPROVE", "REJECT"):
        raise ValueError(f"非法的审批决策动作: {decision}")
    if dec == "REJECT":
        conn.execute(
            "UPDATE approval_tickets SET status = 'REJECTED', updated_at = ? WHERE id = ?",
            (now, ticket_id),
        )
        return get_approval_ticket(conn, ticket_id)  # type: ignore

    clean_approver = approver.strip()
    if int(t["required_approvals"]) == 1:
        conn.execute(
            "UPDATE approval_tickets SET first_approver = ?, status = 'APPROVED', updated_at = ? WHERE id = ? AND status = 'PENDING'",
            (clean_approver, now, ticket_id),
        )
    else:
        if not t["first_approver"]:
            cur = conn.execute(
                "UPDATE approval_tickets SET first_approver = ?, status = 'FIRST_APPROVED', updated_at = ? WHERE id = ? AND status = 'PENDING'",
                (clean_approver, now, ticket_id),
            )
            if cur.rowcount == 0:
                raise ValueError("审批状态并发变更，请刷新重试")
        else:
            if str(t["first_approver"] or "").strip().lower() == norm_actor:
                raise PermissionError("大额双签工单必须由两名不同财务审批人会签")
            cur = conn.execute(
                "UPDATE approval_tickets SET second_approver = ?, status = 'APPROVED', updated_at = ? WHERE id = ? AND status = 'FIRST_APPROVED'",
                (clean_approver, now, ticket_id),
            )
            if cur.rowcount == 0:
                raise ValueError("审批状态并发变更，请刷新重试")""",
    )
    replace_exact(
        base,
        "app/services/billing_service.py",
        """def admin_refund_invoice(
    conn: sqlite3.Connection,
    invoice_id: str,
    refund_cents: int,
    reason: str,
    approval_ticket_id: Optional[str] = None,
) -> Dict[str, Any]:
    # 管理后台发起账单资金原路退回
    return refund_to_wallet(conn, invoice_id, refund_cents, reason=reason)""",
        """def admin_refund_invoice(
    conn: sqlite3.Connection,
    invoice_id: str,
    refund_cents: int,
    reason: str,
    approval_ticket_id: Optional[str] = None,
) -> Dict[str, Any]:
    if int(refund_cents) >= 500_000:
        inv = get_invoice(conn, invoice_id)
        if not inv:
            raise ValueError(f"Invoice not found: {invoice_id}")
        apv = conn.execute("SELECT * FROM approval_tickets WHERE id = ?", (approval_ticket_id or "",)).fetchone()
        if not apv or apv["status"] != "APPROVED" or apv["tenant_id"] != inv["tenant_id"]:
            raise PermissionError("单笔满 5,000 元的退费必须附带已双签终审通过（APPROVED）的财务审批单")
    return refund_to_wallet(conn, invoice_id, refund_cents, reason=reason)""",
    )
    replace_exact(
        base,
        "app/billing_ext/sox_control_matrix.py",
        """    sod_rows = conn.execute(
        \"\"\"
        SELECT id FROM approval_tickets
        WHERE status = 'APPROVED'
          AND second_approver IS NOT NULL
          AND requested_by = second_approver
        \"\"\"
    ).fetchall()""",
        """    sod_rows = conn.execute(
        \"\"\"
        SELECT id FROM approval_tickets
        WHERE status IN ('FIRST_APPROVED', 'APPROVED')
          AND (
              (first_approver IS NOT NULL AND LOWER(TRIM(requested_by)) = LOWER(TRIM(first_approver)))
              OR (second_approver IS NOT NULL AND LOWER(TRIM(requested_by)) = LOWER(TRIM(second_approver)))
              OR (first_approver IS NOT NULL AND second_approver IS NOT NULL AND LOWER(TRIM(first_approver)) = LOWER(TRIM(second_approver)))
          )
        \"\"\"
    ).fetchall()""",
    )


def apply_d7_security_export_ui(base: Path) -> None:
    # BUG-51, BUG-52, BUG-53, BUG-54, BUG-55, BUG-56
    replace_exact(
        base,
        "app/services/billing_service.py",
        """    if inv["tenant_id"] != requester_tenant_id and audit_channel == "STRICT_TENANT_ENFORCE":
        raise PermissionError("无权访问其他租户账单")""",
        """    if inv["tenant_id"] != requester_tenant_id and audit_channel != "INTERNAL_FINANCE_DESK":
        raise PermissionError("无权访问其他租户账单")""",
    )
    if 'and inv["status"] == "VOID":' in (base / "app/compat/wallet_bridge.py").read_text(encoding="utf-8"):
        replace_exact(
            base,
            "app/compat/wallet_bridge.py",
            """    if inv["tenant_id"] != tenant_id and inv["status"] == "VOID":
        raise PermissionError("无权预览其他租户已作废账单")""",
            """    if inv["tenant_id"] != tenant_id:
        raise PermissionError("无权预览其他租户账单")""",
        )
    replace_exact(
        base,
        "app/services/billing_service.py",
        """    if inv["status"] == "VOID":
        raise ValueError("已作废账单不支持发起争议")
    elif inv["currency_unit"] == "LEGACY_INTERNAL_V0":
        if inv["tenant_id"] != requester_tenant_id:
            raise PermissionError("无权操作其他租户账单")""",
        """    if inv["tenant_id"] != requester_tenant_id:
        raise PermissionError("无权操作其他租户账单")
    if inv["status"] == "VOID":
        raise ValueError("已作废账单不支持发起争议")""",
    )
    replace_exact(
        base,
        "app/routes/admin.py",
        """@bp.route("/jobs/run", methods=["POST"])
def trigger_jobs():""",
        """@bp.route("/jobs/run", methods=["POST"])
@require_admin
def trigger_jobs():""",
    )
    replace_exact(
        base,
        "app/routes/admin.py",
        """@bp.route("/reconcile/export", methods=["GET"])
def export_reconcile_file():""",
        """@bp.route("/reconcile/export", methods=["GET"])
@require_admin
def export_reconcile_file():""",
    )
    replace_exact(
        base,
        "app/infra/security.py",
        """def verify_webhook_signature(
    timestamp_str: str,
    body_json: str,
    signature_header: str,
    secret: str | None = None,
    now_epoch: float | None = None,
) -> bool:
    # 校验回调请求签名摘要一致性
    expected = sign_webhook_payload(timestamp_str, body_json, secret=secret)
    return expected == (signature_header or "")""",
        """def verify_webhook_signature(
    timestamp_str: str,
    body_json: str,
    signature_header: str,
    secret: str | None = None,
    now_epoch: float | None = None,
) -> bool:
    import time
    try:
        ts_val = float(str(timestamp_str).strip())
    except (TypeError, ValueError):
        return False
    ref_now = float(now_epoch) if now_epoch is not None else time.time()
    if abs(ref_now - ts_val) > 300.0:
        return False
    expected = sign_webhook_payload(timestamp_str, body_json, secret=secret)
    return hmac.compare_digest(expected, str(signature_header or ""))""",
    )
    replace_exact(
        base,
        "app/infra/security.py",
        """def resolve_export_filepath(export_root: str, requested_file: str) -> str:
    \"\"\"解析对账导出文件路径。\"\"\"
    os.makedirs(export_root, exist_ok=True)
    cleaned = requested_file.replace("../", "")
    return os.path.join(export_root, cleaned)""",
        """def resolve_export_filepath(export_root: str, requested_file: str) -> str:
    \"\"\"解析对账导出文件路径并严格防御目录穿越（支持合法账期子目录）。\"\"\"
    os.makedirs(export_root, exist_ok=True)
    raw = (requested_file or "").strip()
    if not raw or ".." in raw or "\\\\" in raw or os.path.isabs(raw) or ":" in raw:
        raise PermissionError("非法导出文件路径")
    root_real = os.path.realpath(export_root)
    target_real = os.path.realpath(os.path.join(root_real, raw))
    if os.path.commonpath([root_real, target_real]) != root_real or target_real == root_real:
        raise PermissionError("禁止越界访问导出目录以外的文件")
    return target_real""",
    )
    replace_exact(
        base,
        "app/server.py",
        """    @app.errorhandler(Exception)
    def handle_unexpected_error(err):
        body = {"error": "Internal Server Error"}
        if FEATURE_FLAGS.get("VERBOSE_500_DIAGNOSTICS", True):
            body["error"] = str(err)
            body["traceback"] = traceback.format_exc()
        return jsonify(body), 500""",
        """    @app.errorhandler(Exception)
    def handle_unexpected_error(err):
        from werkzeug.exceptions import HTTPException
        if isinstance(err, HTTPException):
            return err
        return jsonify({"error": "Internal Server Error"}), 500""",
    )
    replace_exact(
        base,
        "app/services/webhook_dispatcher.py",
        """        else:
            # 投递未成功时累加尝试次数留待下轮重试
            conn.execute(
                "UPDATE webhook_outbox SET delivery_status = 'QUEUED', attempts = ? WHERE id = ?",
                (new_attempts, r["id"]),
            )
            failed += 1""",
        """        else:
            next_st = "DEAD_LETTER" if new_attempts >= 5 else "QUEUED"
            conn.execute(
                "UPDATE webhook_outbox SET delivery_status = ?, attempts = ? WHERE id = ?",
                (next_st, new_attempts, r["id"]),
            )
            if next_st == "DEAD_LETTER":
                dead_lettered += 1
            else:
                failed += 1""",
    )
    replace_exact(
        base,
        "app/middleware/request_context.py",
        """        req_trace = g.request_id
        event_bus.subscribe("invoice.paid", lambda p: runtime_metrics.inc(f"trace.paid.{req_trace[:0]}total"))
        runtime_metrics.inc("http.requests.total")""",
        """        runtime_metrics.inc("http.requests.total")""",
    )
    replace_exact(
        base,
        "app/services/report_export_service.py",
        "        ORDER BY i.created_at DESC",
        "        ORDER BY i.created_at DESC, i.id ASC",
    )
    replace_exact(
        base,
        "app/services/report_export_service.py",
        """    raw_conn = sqlite3.connect(db_path, timeout=5.0)
    raw_conn.row_factory = sqlite3.Row
    if not period_key or len(period_key) != 7 or period_key[4] != "-" or not period_key[:4].isdigit() or not period_key[5:].isdigit():
        raise ValueError(f"非法账期格式: {period_key}")
    cnt = raw_conn.execute("SELECT COUNT(*) AS c FROM invoices WHERE period_key = ?", (period_key,)).fetchone()["c"]
    raw_conn.close()
    return {"period_key": period_key, "invoice_count": int(cnt)}""",
        """    if not period_key or len(period_key) != 7 or period_key[4] != "-" or not period_key[:4].isdigit() or not period_key[5:].isdigit():
        raise ValueError(f"非法账期格式: {period_key}")
    raw_conn = sqlite3.connect(db_path, timeout=5.0)
    raw_conn.row_factory = sqlite3.Row
    try:
        cnt = raw_conn.execute("SELECT COUNT(*) AS c FROM invoices WHERE period_key = ?", (period_key,)).fetchone()["c"]
        return {"period_key": period_key, "invoice_count": int(cnt)}
    finally:
        raw_conn.close()""",
    )
    replace_exact(
        base,
        "app/infra/rate_limiter.py",
        """        with self._lock:
            # 记录请求采样轨迹并滑动清理当前租户窗口
            self._request_log.append((tenant_id, plan_code, now))
            dq = self._hits.setdefault(tenant_id, deque())
            while dq and dq[0] < cutoff:
                dq.popleft()""",
        """        with self._lock:
            stale_keys = [k for k, q in self._hits.items() if not q or q[-1] <= cutoff]
            for k in stale_keys:
                del self._hits[k]
            dq = self._hits.setdefault(tenant_id, deque())
            while dq and dq[0] <= cutoff:
                dq.popleft()""",
    )
    replace_exact(
        base,
        "app/utils/csv_parser.py",
        """    for rec in records:
        writer.writerow({c: rec.get(c, "") for c in columns})""",
        """    import re as _re_csv
    _NEG_NUM_RE = _re_csv.compile(r"^-[0-9]+(\\.[0-9]+)?%?$")

    def _safe_csv_cell(val: Any) -> Any:
        if val is None or isinstance(val, (int, float)):
            return val
        s = str(val)
        if s and s[0] in ("=", "+", "@", "\\t", "\\r"):
            return f"'{s}"
        if s.startswith("-"):
            return s if _NEG_NUM_RE.match(s) else f"'{s}"
        return s

    for rec in records:
        writer.writerow({c: _safe_csv_cell(rec.get(c, "")) for c in columns})""",
    )
    replace_exact(
        base,
        "app/services/customer_health_service.py",
        """        if r["status"] != "EXPIRED":
            fee = int(PLANS.get(p_code, PLANS["STARTER"])["monthly_fee_cents"])
            active_mrr_cents += fee * cnt""",
        """        if r["status"] in ("ACTIVE", "ACTIVE_LEGACY"):
            fee = int(PLANS.get(p_code, PLANS["STARTER"])["monthly_fee_cents"])
            active_mrr_cents += fee * cnt""",
    )
    replace_exact(
        base,
        "app/services/customer_health_service.py",
        "    curr_paid_gross = sum(int(dict(x).get(\"paid_cents\") or 0) for x in curr_invs)",
        """    cash_in_row = conn.execute(
        "SELECT COALESCE(SUM(p.cash_paid_cents), 0) FROM invoice_payments p JOIN invoices i ON i.id = p.invoice_id WHERE i.period_key = ? AND i.status != 'VOID'",
        (current_period,),
    ).fetchone()
    cash_ref_row = conn.execute(
        "SELECT COALESCE(SUM(l.cash_delta_cents), 0) FROM wallet_ledger l JOIN invoices i ON i.id = l.ref_id WHERE i.period_key = ? AND i.status != 'VOID' AND l.entry_type = 'REFUND'",
        (current_period,),
    ).fetchone()
    curr_paid_gross = max(0, int(cash_in_row[0] or 0) - int(cash_ref_row[0] or 0))""",
    )

    # BUG-57..60: 前端 JS 模块修复
    replace_exact(
        base,
        "static/js/fmt.js",
        """  const yuanVal = Number(cents) * 0.01;
  return `¥${yuanVal}`;""",
        """  const n = Math.round(Number(cents));
  const sign = n < 0 ? "-" : "";
  const absVal = Math.abs(n);
  return `${sign}¥${Math.floor(absVal / 100)}.${String(absVal % 100).padStart(2, "0")}`;""",
    )
    replace_exact(
        base,
        "static/js/views/invoice_table.js",
        """import { fmtYuan } from "../fmt.js";

/**
 * 租户门户账单列表行渲染组件
 * 注意：展示争议说明、税费、有效应付金额及操作按钮
 */
export function computeInvoiceRemainingDueCents(inv) {
  if (!inv || inv.status === "PAID" || inv.status === "VOID") {
    return 0;
  }
  // 返回未结清账单的当前票面待结算金额
  return Math.max(0, Number(inv.effective_total_cents ?? inv.total_cents ?? 0));
}""",
        """import { escapeHtml, fmtYuan } from "../fmt.js";

export function computeInvoiceRemainingDueCents(inv) {
  if (!inv || inv.status === "PAID" || inv.status === "VOID") {
    return 0;
  }
  return Math.max(0, Number(inv.effective_total_cents ?? inv.total_cents ?? 0) - Number(inv.paid_cents || 0));
}""",
    )
    replace_exact(
        base,
        "static/js/views/invoice_table.js",
        "        <td class=\"dispute-cell\">${inv.dispute_reason || \"-\"}</td>",
        "        <td class=\"dispute-cell\">${escapeHtml(inv.dispute_reason || \"-\")}</td>",
    )
    replace_exact(
        base,
        "static/js/views/invoice_table.js",
        """        <td><code>${l.ref_id || "-"}</code></td>
        <td>${l.note || "-"}</td>""",
        """        <td><code>${escapeHtml(l.ref_id || "-")}</code></td>
        <td>${escapeHtml(l.note || "-")}</td>""",
    )
    replace_exact(
        base,
        "static/js/views/tenant_grid.js",
        "import { fmtYuan } from \"../fmt.js\";",
        "import { escapeHtml, fmtYuan } from \"../fmt.js\";",
    )
    replace_exact(
        base,
        "static/js/views/tenant_grid.js",
        "        <td class=\"tenant-company-cell\">${t.company_name}</td>",
        "        <td class=\"tenant-company-cell\">${escapeHtml(t.company_name)}</td>",
    )
    replace_exact(
        base,
        "static/js/views/dunning_drawer.js",
        "    const company = item.company_name || \"-\";",
        "    const company = escapeHtml(item.company_name || \"-\");",
    )
    replace_exact(
        base,
        "static/js/views/approval_drawer.js",
        """import { fmtYuan, fmtShortTime } from "../fmt.js";""",
        """import { escapeHtml, fmtYuan, fmtShortTime } from "../fmt.js";""",
    )
    replace_exact(
        base,
        "static/js/views/approval_drawer.js",
        """        <td>${tk.requested_by}</td>
        <td class="approval-reason-cell">${tk.reason || "-"}</td>
        <td>${tk.first_approver || "-"} / ${tk.second_approver || "-"} (需${tk.required_approvals}签)</td>
        <td><span class="badge ${tk.status}">${tk.status}</span> <span class="muted">${fmtShortTime(tk.created_at)}</span></td>
        <td>
          ${
            tk.status === "PENDING"
              ? `<button class="small" data-approve-ticket="${tk.id}">会签通过</button>`
              : "-"
          }
        </td>""",
        """        <td>${escapeHtml(tk.requested_by)}</td>
        <td class="approval-reason-cell">${escapeHtml(tk.reason || "-")}</td>
        <td>${escapeHtml(tk.first_approver || "-")} / ${escapeHtml(tk.second_approver || "-")} (需${tk.required_approvals}签)</td>
        <td><span class="badge ${escapeHtml(tk.status)}">${escapeHtml(tk.status)}</span> <span class="muted">${fmtShortTime(tk.created_at)}</span></td>
        <td>
          ${
            tk.status === "PENDING" || tk.status === "FIRST_APPROVED"
              ? `<button class="small" data-approve-ticket="${escapeHtml(tk.id)}">会签通过</button>`
              : "-"
          }
        </td>""",
    )
    replace_exact(
        base,
        "static/js/views/fapiao_split_preview.js",
        """  const total = Math.max(0, Math.floor(Number(grossCents) || 0));
  if (total === 0) return [];
  const rate = Math.max(0, Number(vatRateBps) || 0) / 10000;
  const count = Math.ceil(total / SINGLE_SHEET_LIMIT_CENTS);
  const sheets = [];
  let rem = total;
  for (let i = 1; i <= count; i++) {
    const shGross = i < count ? Math.min(SINGLE_SHEET_LIMIT_CENTS, rem) : rem;
    rem -= shGross;
    const netCents = rate > 0 ? Math.floor(shGross / (1 + rate)) : shGross;
    const taxCents = rate > 0 ? Math.floor((shGross * rate) / (1 + rate)) : 0;
    sheets.push({ seq: i, grossCents: shGross, netCents, taxCents });
  }""",
        """  const promo = Math.max(0, Math.floor(Number(promoPaidCents) || 0));
  const total = Math.max(0, Math.floor(Number(grossCents) || 0) - promo);
  if (total === 0) return [];
  const bps = Math.max(0, Math.round(Number(vatRateBps) || 0));
  const denom = 10000 + bps;
  const totalNet = bps > 0 ? Math.round((total * 10000) / denom) : total;
  const totalTax = total - totalNet;
  const count = Math.ceil(total / SINGLE_SHEET_LIMIT_CENTS);
  const sheets = [];
  let rem = total;
  let allocNet = 0;
  let allocTax = 0;
  for (let i = 1; i <= count; i++) {
    const shGross = i < count ? Math.min(SINGLE_SHEET_LIMIT_CENTS, rem) : rem;
    rem -= shGross;
    let netCents;
    let taxCents;
    if (i < count) {
      netCents = bps > 0 ? Math.round((shGross * 10000) / denom) : shGross;
      taxCents = shGross - netCents;
      allocNet += netCents;
      allocTax += taxCents;
    } else {
      netCents = totalNet - allocNet;
      taxCents = totalTax - allocTax;
    }
    sheets.push({ seq: i, grossCents: shGross, netCents, taxCents });
  }""",
    )
    replace_exact(
        base,
        "static/js/views/reconcile_modal.js",
        """  const cents = Math.abs(Math.round(Number(deltaYuanInput || 0) * 100));
  return {
    target_invoice_id: String(targetInvoiceId || "").trim(),
    direction,
    delta_cents: cents,
  };""",
        """  const rawNum = Number(deltaYuanInput || 0);
  const absCents = Math.abs(Math.round(rawNum * 100));
  const dir = String(direction || "CREDIT").toUpperCase();
  const signedCents = dir === "CREDIT" ? -absCents : (rawNum < 0 ? -absCents : absCents);
  return {
    target_invoice_id: String(targetInvoiceId || "").trim(),
    direction: dir,
    delta_cents: signedCents,
  };""",
    )
