# -*- coding: utf-8 -*-
"""基础主链路冒烟测试（仅覆盖常规正常请求路径）。"""
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from app.server import create_app


class SmokeTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="yunce_smoke_")
        src_db = Path(__file__).resolve().parent.parent / "data" / "yunce_billing.db"
        self.db_path = os.path.join(self.tmp_dir, "yunce_billing.db")
        shutil.copy2(src_db, self.db_path)
        self.app = create_app(db_path=self.db_path)
        self.client = self.app.test_client()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_health(self):
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["status"], "ok")

    def test_normal_tenant_subscription_and_usage(self):
        headers = {"X-Tenant-Token": "tok_cust_008"}
        res = self.client.get("/api/subscriptions/current?period_key=2026-11", headers=headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["quota"]["plan_code"], "STARTER")

        res2 = self.client.post(
            "/api/usage/events",
            headers=headers,
            json={"quantity": 120, "period_key": "2026-11"},
        )
        self.assertEqual(res2.status_code, 201)

    def test_legacy_tenant_read(self):
        res = self.client.get(
            "/api/subscriptions/current?period_key=2026-11",
            headers={"X-Tenant-Token": "tok_leg_001"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["quota"]["plan_code"], "LEGACY_FLAT_99")

    def test_wallet_topup_smoke(self):
        before = self.client.get("/api/wallet", headers={"X-Tenant-Token": "tok_cust_008"}).get_json()["wallet"]["cash_balance_cents"]
        res = self.client.post(
            "/api/wallet/topup",
            headers={"X-Tenant-Token": "tok_cust_008"},
            json={"amount_cents": 5000},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["wallet"]["cash_balance_cents"], before + 5000)


if __name__ == "__main__":
    unittest.main()
