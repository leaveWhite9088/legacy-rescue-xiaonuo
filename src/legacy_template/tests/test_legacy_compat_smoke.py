# -*- coding: utf-8 -*-
"""2024 V1 存量老租户（ACTIVE_LEGACY / YUAN_STR / LEGACY_FLAT_99）基础解析与计费守护测试。"""
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from app.domain.pricing import calculate_cycle_bill
from app.infra.db import get_connection, parse_legacy_amount_cents
from app.server import create_app


class LegacyCompatSmokeTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="yunce_leg_")
        src_db = Path(__file__).resolve().parent.parent / "data" / "yunce_billing.db"
        self.db_path = os.path.join(self.tmp_dir, "yunce_billing.db")
        shutil.copy2(src_db, self.db_path)
        self.app = create_app(db_path=self.db_path)
        self.client = self.app.test_client()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_yuan_str_currency_shim_parsing(self):
        row = {"currency_unit": "YUAN_STR", "raw_legacy_total": "¥1,288.50", "total_cents": 0}
        self.assertEqual(parse_legacy_amount_cents(row, "total_cents"), 128850)

    def test_legacy_flat_99_contract_billing_intact(self):
        conn = get_connection(self.db_path)
        try:
            leg = conn.execute("SELECT id FROM tenants WHERE status = 'ACTIVE_LEGACY' ORDER BY id ASC LIMIT 1").fetchone()
            self.assertIsNotNone(leg)
            bill = calculate_cycle_bill(conn, leg["id"], "2026-11", "LEGACY_FLAT_99")
            self.assertGreaterEqual(bill["total_cents"], 0)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
