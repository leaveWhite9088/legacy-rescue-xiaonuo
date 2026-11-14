# -*- coding: utf-8 -*-
"""经营分析、ASC 606 收入瀑布、SOX 诊断与套餐沙盘扩展接口常规测试。"""
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from app.infra.config import ADMIN_API_KEY
from app.server import create_app


class ReportingAndExtensionsTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="yunce_rep_")
        src_db = Path(__file__).resolve().parent.parent / "data" / "yunce_billing.db"
        self.db_path = os.path.join(self.tmp_dir, "yunce_billing.db")
        shutil.copy2(src_db, self.db_path)
        self.app = create_app(db_path=self.db_path)
        self.client = self.app.test_client()
        self.admin_headers = {"X-Admin-Key": ADMIN_API_KEY}

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_analytics_mrr_and_asc606_endpoints(self):
        r1 = self.client.get("/api/admin/analytics/mrr", headers=self.admin_headers)
        self.assertEqual(r1.status_code, 200)
        self.assertIn("mrr", r1.get_json())

        r2 = self.client.get("/api/admin/analytics/asc606/2026-10", headers=self.admin_headers)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.get_json()["period_key"], "2026-10")

        r3 = self.client.get("/api/admin/analytics/vat-workpaper/2026-10", headers=self.admin_headers)
        self.assertEqual(r3.status_code, 200)

    def test_diagnostics_sox_and_plan_simulator(self):
        sox = self.client.get("/api/admin/diagnostics/sox-controls", headers=self.admin_headers)
        self.assertEqual(sox.status_code, 200)
        self.assertEqual(sox.get_json()["total_controls"], 6)

        sim = self.client.get("/api/admin/diagnostics/plan-simulator?calls=85000", headers=self.admin_headers)
        self.assertEqual(sim.status_code, 200)
        self.assertIn(sim.get_json()["recommended_plan_code"], ("STARTER", "PRO", "ENTERPRISE"))

        pbc = self.client.get("/api/admin/diagnostics/pbc-bundle/2026-10", headers=self.admin_headers)
        self.assertEqual(pbc.status_code, 200)
        self.assertTrue(pbc.get_json()["workpapers"]["schedule_A_three_way_tieout"]["general_ledger_leg"]["trial_balance_matched"])


if __name__ == "__main__":
    unittest.main()
