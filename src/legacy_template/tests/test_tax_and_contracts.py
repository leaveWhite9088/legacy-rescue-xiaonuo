# -*- coding: utf-8 -*-
"""税率计算、累进阶梯与大客户保底合同单元测试。"""
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from app.domain.contracts import apply_enterprise_contract_terms
from app.domain.pricing import compute_late_fee_cents, compute_tiered_overage_cents
from app.domain.tax_engine import compute_tax_breakdown
from app.infra.config import PLANS
from app.infra.db import get_connection


class TaxAndContractsTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="yunce_tax_")
        src_db = Path(__file__).resolve().parent.parent / "data" / "yunce_billing.db"
        self.db_path = os.path.join(self.tmp_dir, "yunce_billing.db")
        shutil.copy2(src_db, self.db_path)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_progressive_marginal_tiering(self):
        pro_tiers = PLANS["PRO"]["overage_tiers"]
        self.assertEqual(compute_tiered_overage_cents(120000, 50000, pro_tiers), 120000)

    def test_tax_profiles(self):
        inc = compute_tax_breakdown(59900, "CN_VAT_6_INCLUSIVE")
        self.assertEqual(inc["tax_added_cents"], 0)
        self.assertEqual(inc["gross_total_cents"], 59900)

        exc = compute_tax_breakdown(59900, "CN_VAT_6_EXCLUSIVE")
        self.assertEqual(exc["tax_added_cents"], 3594)
        self.assertEqual(exc["gross_total_cents"], 63494)

        sg = compute_tax_breakdown(10000, "SG_GST_9_EXCLUSIVE")
        self.assertEqual(sg["tax_added_cents"], 900)
        self.assertEqual(sg["gross_total_cents"], 10900)

    def test_enterprise_minimum_commit_contract(self):
        conn = get_connection(self.db_path)
        try:
            row = conn.execute("SELECT tenant_id FROM enterprise_contracts WHERE status = 'ACTIVE' LIMIT 1").fetchone()
            self.assertIsNotNone(row)
            res = apply_enterprise_contract_terms(conn, row["tenant_id"], base_fee_cents=199900, overage_fee_cents=10000)
            self.assertTrue(res["has_contract"])
            self.assertEqual(res["subtotal_cents"], 220000)
        finally:
            conn.close()

    def test_uniform_late_fee_rule(self):
        self.assertEqual(compute_late_fee_cents(59900, is_overdue=True), 2995)
        self.assertEqual(compute_late_fee_cents(59900, is_overdue=False), 0)


if __name__ == "__main__":
    unittest.main()
