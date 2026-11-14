# -*- coding: utf-8 -*-
"""边缘网关计量标准化、令牌桶限流推演与银行清算工作日顺延测试。"""
import unittest

from app.audit_compliance_archive.bank_clearing_calendar_cn import next_cnaps_settlement_date
from app.gateway_ingest.edge_cdr_normalizer_v2 import RawGatewayAccessRecord, normalize_gateway_batch
from app.gateway_ingest.token_bucket_limiter_sim import simulate_token_bucket_traffic_burst
from app.legacy_ops_2024.legacy_csv_importer_2024 import parse_multibank_statement_csv_2024


class GatewayAndReconUnitTestCase(unittest.TestCase):
    def test_gateway_5xx_exempt_and_weight_multiplier(self):
        batch = [
            RawGatewayAccessRecord("req_1", "cust_008", "STANDARD_TEXT_EVAL", 200, 100, "cn-east-1", "2026-11-10T08:00:00Z"),
            RawGatewayAccessRecord("req_2", "cust_008", "MULTIMODAL_DOC_OCR", 200, 20, "cn-east-1", "2026-11-10T08:01:00Z"),
            RawGatewayAccessRecord("req_3", "cust_008", "STANDARD_TEXT_EVAL", 503, 500, "cn-east-1", "2026-11-10T08:02:00Z"),
        ]
        res = normalize_gateway_batch(batch)
        self.assertEqual(res["billable_event_count"], 2)
        self.assertEqual(res["exempt_record_count"], 1)
        self.assertEqual(res["total_billable_standard_units"], 100 + 20 * 5)

    def test_token_bucket_and_cnaps_calendar(self):
        burst = simulate_token_bucket_traffic_burst("STARTER", [50, 50, 50], wallet_total_cents=10_000)
        self.assertEqual(burst["circuit_breaker"], "CLOSED_NORMAL")
        self.assertGreater(burst["admitted_requests"], 0)

        # 国庆假期顺延至节后首个工作日
        settle = next_cnaps_settlement_date("2026-10-01", lag_workdays=1)
        self.assertGreaterEqual(settle["expected_clearing_date"], "2026-10-08")

    def test_multibank_csv_alias_parser(self):
        csv_text = "交易流水号,对方户名,对方账号,贷方发生额,交易日期,附言\nICBC20261101001,上海云测客户A,6222021001112222,199.00,2026-11-01,月结款 t_008\n"
        parsed = parse_multibank_statement_csv_2024(csv_text)
        self.assertEqual(len(parsed["rows"]), 1)
        self.assertEqual(parsed["rows"][0]["amount_cents"], 19900)
        self.assertEqual(parsed["rows"][0]["inferred_tenant_hint"], "t_008")


if __name__ == "__main__":
    unittest.main()
