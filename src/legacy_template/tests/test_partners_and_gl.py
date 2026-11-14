# -*- coding: utf-8 -*-
"""渠道返佣与总账借贷平衡测试。"""
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from app.infra.config import ADMIN_API_KEY
from app.server import create_app


class PartnersAndGLTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="yunce_gl_")
        src_db = Path(__file__).resolve().parent.parent / "data" / "yunce_billing.db"
        self.db_path = os.path.join(self.tmp_dir, "yunce_billing.db")
        shutil.copy2(src_db, self.db_path)
        self.app = create_app(db_path=self.db_path)
        self.client = self.app.test_client()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_partner_commissions_endpoint(self):
        res = self.client.get(
            "/api/partners/commissions?period_key=2026-10",
            headers={"X-Admin-Key": ADMIN_API_KEY},
        )
        self.assertEqual(res.status_code, 200)
        items = res.get_json()["commissions"]
        self.assertGreater(len(items), 0)

    def test_gl_journal_debits_equal_credits(self):
        res = self.client.get(
            "/api/admin/gl/2026-10",
            headers={"X-Admin-Key": ADMIN_API_KEY},
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["balanced"])
        self.assertEqual(data["total_debit_cents"], data["total_credit_cents"])
        self.assertGreater(len(data["entries"]), 0)


if __name__ == "__main__":
    unittest.main()
