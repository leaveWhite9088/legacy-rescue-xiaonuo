# -*- coding: utf-8 -*-
"""数电发票开具、红字冲销及财务双签审批流常规冒烟测试。"""
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from app.infra.config import ADMIN_API_KEY
from app.server import create_app


class FapiaoAndApprovalsTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="yunce_fapiao_")
        src_db = Path(__file__).resolve().parent.parent / "data" / "yunce_billing.db"
        self.db_path = os.path.join(self.tmp_dir, "yunce_billing.db")
        shutil.copy2(src_db, self.db_path)
        self.app = create_app(db_path=self.db_path)
        self.client = self.app.test_client()
        self.admin_headers = {"X-Admin-Key": ADMIN_API_KEY}

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_fapiao_apply_and_red_letter_reversal(self):
        # 选取一张常规已付账单测试正常蓝票申请与管理员红冲
        tenant_headers = {"X-Tenant-Token": "tok_cust_008"}
        invs = self.client.get("/api/invoices?period_key=2026-09", headers=tenant_headers).get_json()["invoices"]
        paid_invs = [x for x in invs if x["status"] == "PAID" and x["total_cents"] > 0]
        self.assertTrue(len(paid_invs) >= 1)
        target_inv = paid_invs[0]

        res = self.client.post(
            "/api/fapiao/apply",
            headers=tenant_headers,
            json={
                "invoice_id": target_inv["id"],
                "buyer_tax_id": "91310115MA1K3B0B3G",
                "fapiao_type": "VAT_SPECIAL_E",
            },
        )
        self.assertEqual(res.status_code, 201)
        fapiao_id = res.get_json()["id"]

        red = self.client.post(f"/api/fapiao/{fapiao_id}/red-letter", headers=self.admin_headers)
        self.assertEqual(red.status_code, 200)
        self.assertEqual(red.get_json()["status"], "RED_ISSUED")

    def test_dual_sign_approval_workflow(self):
        # 大额（>= 500,000 分）审批单需双人复核方可转为 APPROVED
        create_res = self.client.post(
            "/api/admin/approvals",
            headers=self.admin_headers,
            json={
                "ticket_type": "MANUAL_CREDIT_ADJUSTMENT",
                "tenant_id": "t_cust_008",
                "ref_object_id": "inv_demo_ref",
                "amount_cents": 600_000,
                "requested_by": "ops_alice",
                "reason": "年度框架返利申请",
            },
        )
        self.assertEqual(create_res.status_code, 201)
        ticket = create_res.get_json()
        self.assertEqual(ticket["required_approvals"], 2)

        step1 = self.client.post(
            f"/api/admin/approvals/{ticket['id']}/decide",
            headers=self.admin_headers,
            json={"approver": "fin_bob", "decision": "APPROVE"},
        )
        self.assertEqual(step1.status_code, 200)
        self.assertEqual(step1.get_json()["status"], "FIRST_APPROVED")

        step2 = self.client.post(
            f"/api/admin/approvals/{ticket['id']}/decide",
            headers=self.admin_headers,
            json={"approver": "cfo_carol", "decision": "APPROVE"},
        )
        self.assertEqual(step2.status_code, 200)
        self.assertEqual(step2.get_json()["status"], "APPROVED")


if __name__ == "__main__":
    unittest.main()
