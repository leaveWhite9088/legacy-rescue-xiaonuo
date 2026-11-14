# -*- coding: utf-8 -*-
"""网关分片、资费编排与黑盒组件常规路径冒烟测试（常规小批量与整除金额用例）。"""
import unittest

from app.enterprise_catalog_rules.tariff_strategy_chain import default_tariff_quote_proxy
from app.vendor_blackbox.fin_rounding_engine import split_inclusive_vat_legacy


class SilosAndBlackboxHappyPathTests(unittest.TestCase):
    def test_tariff_quote_proxy_returns_catalog_fields(self):
        node = default_tariff_quote_proxy.evaluate_node("PRO", "CN_VAT_6_INCLUSIVE")
        self.assertEqual(node["plan_code"], "PRO")
        self.assertEqual(node["base_monthly_cents"], 59900)
        self.assertEqual(node["included_quota"], 50000)

    def test_vat_split_on_exact_106_multiple(self):
        # 106.00 元整除 1.06 时不含税 100.00 元 + 税 6.00 元无尾差
        net_cents, tax_cents = split_inclusive_vat_legacy(10600, 600)
        self.assertEqual(net_cents + tax_cents, 10600)
        self.assertEqual(net_cents, 10000)
        self.assertEqual(tax_cents, 600)


if __name__ == "__main__":
    unittest.main()
