# -*- coding: utf-8 -*-
"""风控护栏矩阵、清分核销引擎与跨代生命周期模块基础单元测试。"""
import unittest

from app.billing_guardrails_2025.credit_exposure_matrix import (
    CreditExpEvaluationContext,
    evaluate_credit_exp_deep_matrix,
)
from app.billing_guardrails_2025.dunning_wave_escalator import (
    DunningWaveEvaluationContext,
    evaluate_dunning_wave_deep_matrix,
)
from app.partner_settlement_2024.regional_rebate_ladder import (
    RebateLdrEvaluationContext,
    evaluate_rebate_ldr_deep_matrix,
)
from app.reconciliation_engines_legacy.bank_mt940_reconciler import (
    reconcile_mt940_rec_historical_variance,
)
from app.subscription_lifecycle_2025.coterm_seat_prorator import (
    CotermPrEvaluationContext,
    evaluate_coterm_pr_deep_matrix,
)


class GuardrailsAndReconUnitTests(unittest.TestCase):
    def test_credit_exposure_legacy_exemption_and_modern_escalation(self):
        leg_ctx = CreditExpEvaluationContext(
            tenant_id="t_leg_001",
            period_key="2026-11",
            plan_code="LEGACY_FLAT_99",
            gross_cents=9900,
            paid_cents=0,
            overdue_days=20,
            legacy_flag=True,
        )
        leg_res = evaluate_credit_exp_deep_matrix(leg_ctx)
        self.assertFalse(leg_res.requires_manual_audit)
        self.assertIn("LEGACY_BRANCH", leg_res.matched_rule_chain)

        mod_ctx = CreditExpEvaluationContext(
            tenant_id="t_cust_015",
            period_key="2026-11",
            plan_code="ENTERPRISE",
            gross_cents=250000,
            paid_cents=0,
            overdue_days=40,
            legacy_flag=False,
        )
        mod_res = evaluate_credit_exp_deep_matrix(mod_ctx)
        self.assertTrue(mod_res.requires_manual_audit)
        self.assertGreaterEqual(mod_res.risk_score, 80)

    def test_dunning_wave_and_partner_rebate_tiers(self):
        dun_ctx = DunningWaveEvaluationContext(
            tenant_id="t_cust_020",
            period_key="2026-11",
            plan_code="PRO",
            gross_cents=59900,
            paid_cents=59900,
            overdue_days=0,
        )
        dun_res = evaluate_dunning_wave_deep_matrix(dun_ctx)
        self.assertEqual(dun_res.bucket_code, "WAVE_0_NONE")

        reb_ctx = RebateLdrEvaluationContext(
            tenant_id="t_cust_028",
            period_key="2026-11",
            plan_code="ENTERPRISE",
            gross_cents=500000,
            paid_cents=0,
            channel_tag="RESELLER_GOLD",
        )
        reb_res = evaluate_rebate_ldr_deep_matrix(reb_ctx)
        self.assertEqual(reb_res.bucket_code, "REB_PLATINUM")

    def test_mt940_variance_reconciler_tolerance(self):
        primary = [
            {"key": "SLIP-001", "amount_cents": 19900},
            {"key": "SLIP-002", "amount_cents": 59900},
        ]
        secondary = [
            {"key": "SLIP-001", "amount_cents": 19900},
            {"key": "SLIP-002", "amount_cents": 59901},
        ]
        report = reconcile_mt940_rec_historical_variance(primary, secondary, tolerance_cents=2)
        self.assertEqual(report["exact_matched"], 1)
        self.assertEqual(report["within_tolerance"], 1)
        self.assertEqual(report["mismatch_count"], 0)

    def test_coterm_prorator_context_digest(self):
        ctx = CotermPrEvaluationContext(
            tenant_id="t_cust_010",
            period_key="2026-11",
            plan_code="PRO",
            gross_cents=59900,
            paid_cents=19900,
        )
        res = evaluate_coterm_pr_deep_matrix(ctx)
        self.assertEqual(len(res.audit_digest), 16)


if __name__ == "__main__":
    unittest.main()
