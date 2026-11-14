from app.legacy_erp_batch_2025.golden_tax_bureau_csv_exporter import export_golden_tax_batch_import_csv
from app.legacy_erp_batch_2025.kingdee_kis_fixed_width_bridge import format_kingdee_kis_fixed_width_lines, parse_kingdee_kis_fixed_width_lines
from app.legacy_erp_batch_2025.statement_diff_comparator import compare_customer_ap_vs_platform_ar
from app.legacy_erp_batch_2025.ufida_nc_xml_voucher_validator import build_ufinterface_gl_voucher_xml, validate_ufinterface_gl_voucher_xml
# -*- coding: utf-8 -*-
"""B2B EDI 电子报文（MT940/cXML/camt.053）、IFRS-15 合同变更准则、拆票尾差守恒与银企互联单元测试。"""
import unittest

from app.billing_ext.late_fee_waiver_policy_checker import evaluate_late_fee_waiver_request
from app.billing_ext.vat_invoice_split_engine import plan_fapiao_sheet_splits
from app.connectors.cmb_cbs_treasury_xml import parse_cmb_cbs_trans_response_xml
from app.connectors.icbc_directlink_batch import parse_icbc_b2e_pipe_batch
from app.edi_b2b_exchange.ariba_cxml_invoice_builder import build_ariba_cxml_invoice_payload
from app.edi_b2b_exchange.iso20022_camt053_extractor import extract_camt053_entries
from app.edi_b2b_exchange.swift_mt940_parser import parse_swift_mt940_message
from app.legacy_v1.v1_pdf_postscript_writer import build_minimal_invoice_pdf14_bytes
from app.legacy_v1.v1_prepaid_card_ledger import mint_prepaid_card_batch_preview, verify_prepaid_card_number
from app.revenue_accounting_ifrs15.asc340_commission_capitalizer import build_commission_capitalization_schedule
from app.revenue_accounting_ifrs15.contract_modification_accounting import evaluate_ifrs15_contract_modification


class EdiIfrsAndConnectorsTestCase(unittest.TestCase):
    def test_swift_mt940_balance_reconciliation(self):
        sample_mt940 = "\n".join([
            ":20:STMT20261112",
            ":25:HK8800123456",
            ":60F:C261111USD1000,00",
            ":61:261112C250,50NTRFCUST_SG_01//SEQ01",
            ":86:INVOICE SETTLEMENT NOV",
            ":62F:C261112USD1250,50",
        ])
        parsed = parse_swift_mt940_message(sample_mt940)
        self.assertTrue(parsed["balance_reconciled"])
        self.assertEqual(parsed["computed_closing_minor"], 125050)

    def test_ariba_cxml_and_camt053(self):
        cxml = build_ariba_cxml_invoice_payload(
            {"id": "inv_test_01", "plan_code": "PRO", "base_fee_cents": 59900, "overage_fee_cents": 1000, "tax_cents": 0, "total_cents": 60900},
            buyer_network_id="AN029911",
            po_number="PO-2026-77",
        )
        self.assertIn("InvoiceDetailRequest", cxml["cxml_document"])

        camt = extract_camt053_entries(
            '<Document><BkToCstmrStmt><Stmt><Id>S1</Id><Ntry><Amt Ccy="CNY">599.00</Amt><CdtDbtInd>CRDT</CdtDbtInd></Ntry></Stmt></BkToCstmrStmt></Document>'
        )
        self.assertEqual(camt["total_credit_cents"], 59900)

    def test_ifrs15_modification_and_asc340_commission(self):
        mod = evaluate_ifrs15_contract_modification(
            original_total_price_cents=1_200_000,
            original_total_months=12,
            elapsed_months=6,
            already_recognized_rev_cents=600_000,
            added_price_cents=900_000,
            added_months=6,
            is_distinct_remaining_service=True,
            priced_at_standalone_ssp=False,
        )
        self.assertEqual(mod["treatment_code"], "CASE_B_PROSPECTIVE_TERMINATION_AND_REPLACEMENT")

        cap = build_commission_capitalization_schedule("DEAL-88", 360_000, contract_months=24, expected_customer_benefit_months=36)
        self.assertTrue(cap["capitalized"])
        self.assertEqual(len(cap["monthly_schedule"]), 36)

    def test_fapiao_split_penny_conservation_and_late_fee_gate(self):
        split = plan_fapiao_sheet_splits("inv_whale_01", 23_456_789, vat_rate_bps=600)
        self.assertEqual(split["sheet_count"], 3)
        self.assertTrue(split["penny_conserved"])

        waiver = evaluate_late_fee_waiver_request(100_000, 5_000, "VIP_STRATEGIC_ACCOUNT")
        self.assertFalse(waiver["waiver_approved"])

    def test_prepaid_card_luhn_pdf_and_bank_adapters(self):
        cards = mint_prepaid_card_batch_preview("YC24_CASH_500", start_serial=101, count=3)
        self.assertTrue(all(verify_prepaid_card_number(c.card_number) for c in cards))

        pdf_bytes = build_minimal_invoice_pdf14_bytes({"id": "inv_01", "total_cents": 19900}, "cust_008")
        self.assertTrue(pdf_bytes.startswith(b"%PDF-1.4"))

        cmb = parse_cmb_cbs_trans_response_xml(
            "<CMBSDKPGK><INFO><RETCOD>0</RETCOD></INFO><NTQTSINFZ><AMTCDR>C</AMTCDR><TRSAMT>199.00</TRSAMT><REQNBR>R1</REQNBR></NTQTSINFZ></CMBSDKPGK>"
        )
        self.assertTrue(cmb["ok"])
        self.assertEqual(cmb["total_credit_cents"], 19900)

        icbc = parse_icbc_b2e_pipe_batch("HDR|622202|20261112|1|59900\nDTL|SEQ1|C|59900|客户甲|货款")
        self.assertTrue(icbc["control_matched"])


    def test_erp2025_ufida_kingdee_and_bureau_export(self):
        xml_doc = build_ufinterface_gl_voucher_xml(
            "V-202611-01",
            "2026",
            "11",
            [
                {"account_code": "112201", "debit_cents": 19900, "credit_cents": 0, "customer_aux_code": "CUST_008"},
                {"account_code": "600101", "debit_cents": 0, "credit_cents": 19900},
            ],
        )
        v_res = validate_ufinterface_gl_voucher_xml(xml_doc)
        self.assertTrue(v_res["valid"])

        fw = format_kingdee_kis_fixed_width_lines([{"id": "inv_1", "tenant_id": "cust_008", "period_key": "2026-11", "plan_code": "STARTER", "total_cents": 19900, "status": "PAID"}])
        self.assertEqual(parse_kingdee_kis_fixed_width_lines(fw)[0]["total_cents"], 19900)

        gt = export_golden_tax_batch_import_csv([{"id": "FP1", "buyer_name": "上海测试企业", "buyer_tax_id": "91310115MA1K3B0B3G", "fapiao_type": "VAT_SPECIAL_E", "gross_amount_cents": 10600, "tax_amount_cents": 600}])
        self.assertEqual(gt["exported_row_count"], 1)

        diff = compare_customer_ap_vs_platform_ar(
            [{"invoice_id": "inv_x", "recorded_cents": 10000}],
            [{"id": "inv_x", "total_cents": 10600, "tax_cents": 600}],
        )
        self.assertEqual(diff["variances"][0]["category"], "CUSTOMER_BOOKED_PRETAX_EXCLUDING_EXCLUSIVE_VAT")


if __name__ == "__main__":
    unittest.main()
