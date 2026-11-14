# -*- coding: utf-8 -*-
"""2025 H1 混合云硬件租赁（13% 增值税率）与 SaaS 软件订阅（6% 增值税率）捆绑合同拆分器。"""
from typing import Dict


def split_bundled_hardware_saas_contract(
    bundle_gross_cents: int,
    hardware_fair_value_cents: int,
    saas_fair_value_cents: int,
) -> Dict[str, int]:
    """按单独售价（SSP - Standalone Selling Price）相对比例分摊捆绑合同交易对价。"""
    gross = max(0, int(bundle_gross_cents))
    hw_fv = max(0, int(hardware_fair_value_cents))
    sw_fv = max(1, int(saas_fair_value_cents))
    total_fv = hw_fv + sw_fv

    hw_alloc = int(round((gross * hw_fv) / float(total_fv)))
    sw_alloc = gross - hw_alloc
    hw_net = int(round((hw_alloc * 10000.0) / 11300.0))
    sw_net = int(round((sw_alloc * 10000.0) / 10600.0))
    return {
        "hardware_gross_13pct_cents": hw_alloc,
        "hardware_net_cents": hw_net,
        "hardware_vat_cents": hw_alloc - hw_net,
        "saas_gross_6pct_cents": sw_alloc,
        "saas_net_cents": sw_net,
        "saas_vat_cents": sw_alloc - sw_net,
    }
