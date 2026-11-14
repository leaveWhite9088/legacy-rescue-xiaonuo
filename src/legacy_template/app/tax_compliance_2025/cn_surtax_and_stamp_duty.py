# -*- coding: utf-8 -*-
"""中国境内主体增值税附加税费（城建税7% + 教育费附加3% + 地方教育附加2%）与技术合同印花税（0.03%）计提引擎。"""
from typing import Dict


URBAN_MAINT_BPS = 700
EDU_SURCHARGE_BPS = 300
LOCAL_EDU_BPS = 200
TECH_CONTRACT_STAMP_BPS = 3  # 万分之三


def estimate_monthly_cn_surtaxes(
    output_vat_cents: int,
    creditable_input_vat_cents: int,
    signed_contract_net_cents: int,
    small_taxpayer_half_relief: bool = False,
) -> Dict[str, int]:
    payable_vat = max(0, int(output_vat_cents) - int(creditable_input_vat_cents))
    combined_surtax_bps = URBAN_MAINT_BPS + EDU_SURCHARGE_BPS + LOCAL_EDU_BPS
    raw_surtax = (payable_vat * combined_surtax_bps + 5000) // 10000
    raw_stamp = (max(0, int(signed_contract_net_cents)) * TECH_CONTRACT_STAMP_BPS + 5000) // 10000

    if small_taxpayer_half_relief:
        raw_surtax = (raw_surtax + 1) // 2
        raw_stamp = (raw_stamp + 1) // 2

    return {
        "net_payable_vat_cents": payable_vat,
        "surtaxes_total_cents": raw_surtax,
        "stamp_duty_cents": raw_stamp,
        "total_tax_provision_cents": payable_vat + raw_surtax + raw_stamp,
    }
