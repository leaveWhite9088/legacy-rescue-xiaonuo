# -*- coding: utf-8 -*-
"""CRM 商机续约雷达、司库 13 周现金流预测、收单通道寻优与 FinOps 毛利分摊单元测试。"""
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from app.crm_sync.onboarding_provisioning_saga import evaluate_tenant_onboarding_readiness
from app.crm_sync.salesforce_opportunity_mapper import CrmOpportunityPayload, map_opportunity_to_booking_metrics
from app.infra.config import ADMIN_API_KEY
from app.server import create_app


class CrmAndTreasuryTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="yunce_treas_")
        src_db = Path(__file__).resolve().parent.parent / "data" / "yunce_billing.db"
        self.db_path = os.path.join(self.tmp_dir, "yunce_billing.db")
        shutil.copy2(src_db, self.db_path)
        self.app = create_app(db_path=self.db_path)
        self.client = self.app.test_client()
        self.admin_headers = {"X-Admin-Key": ADMIN_API_KEY}

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_crm_booking_metrics_and_onboarding_guard(self):
        opp = CrmOpportunityPayload(
            opp_id="OPP-2026-901",
            account_name="华东智造集团",
            stage_code="05_CLOSED_WON",
            target_plan_code="ENTERPRISE",
            contract_term_months=12,
            quoted_currency="CNY",
            quoted_monthly_commit_minor=250_000,
        )
        metrics = map_opportunity_to_booking_metrics(opp)
        self.assertEqual(metrics["arr_cents"], 3_000_000)

        # 新租户严禁新签 LEGACY_FLAT_99
        blocked = evaluate_tenant_onboarding_readiness({"company_name": "新锐科技", "plan_code": "LEGACY_FLAT_99"})
        self.assertFalse(blocked["ready_to_provision"])

    def test_treasury_forecast_and_finops_routes(self):
        t_res = self.client.get("/api/admin/analytics/treasury-forecast", headers=self.admin_headers)
        self.assertEqual(t_res.status_code, 200)
        self.assertEqual(len(t_res.get_json()["forecast_13w"]["weekly_schedule"]), 13)

        ch_res = self.client.get("/api/admin/analytics/channel-router?amount_cents=200000", headers=self.admin_headers)
        self.assertEqual(ch_res.status_code, 200)
        self.assertTrue(ch_res.get_json()["routed"])

        fm_res = self.client.get("/api/admin/analytics/finops-margins/2026-10", headers=self.admin_headers)
        self.assertEqual(fm_res.status_code, 200)
        self.assertGreater(fm_res.get_json()["gross_margins"]["total_net_revenue_cents"], 0)

        rad_res = self.client.get("/api/admin/diagnostics/renewal-radar", headers=self.admin_headers)
        self.assertEqual(rad_res.status_code, 200)


if __name__ == "__main__":
    unittest.main()
