# -*- coding: utf-8 -*-
"""2023-2024 旧版地区税目静态映射表与普票/专票税控盘编码表（历史遗留模块）。
生产计税请统一调用 app.domain.tax_engine.compute_tax_breakdown！
"""
from typing import Any, Dict, List

GOLDEN_TAX_GOODS_CATALOG_V1: Dict[str, Dict[str, Any]] = {
    "SAAS_SUBSCRIPTION": {
        "spbm": "3040201010000000000",
        "item_name": "*现代服务*云策SaaS平台基础订阅服务费",
        "default_vat_bps": 600,
        "zero_tax_eligible": False,
    },
    "API_METERING_OVERAGE": {
        "spbm": "3040201020000000000",
        "item_name": "*现代服务*接口弹性计算超额调用服务费",
        "default_vat_bps": 600,
        "zero_tax_eligible": False,
    },
    "CROSS_BORDER_SAAS": {
        "spbm": "3040201990000000000",
        "item_name": "*现代服务*离岸技术信息咨询与云服务",
        "default_vat_bps": 0,
        "zero_tax_eligible": True,
    },
    "CONTRACT_MIN_COMMIT_TOPUP": {
        "spbm": "3040201030000000000",
        "item_name": "*现代服务*企业框架协议保底容量服务费",
        "default_vat_bps": 600,
        "zero_tax_eligible": False,
    },
}

PROVINCE_TAX_BUREAU_CODES = {
    "3100": "上海市税务局",
    "3300": "浙江省税务局",
    "3302": "宁波市税务局",
    "3200": "江苏省税务局",
    "4400": "广东省税务局",
    "4403": "深圳市税务局",
    "1100": "北京市税务局",
}


def lookup_golden_tax_spbm(line_type: str, is_export_exempt: bool = False) -> Dict[str, Any]:
    if is_export_exempt:
        return dict(GOLDEN_TAX_GOODS_CATALOG_V1["CROSS_BORDER_SAAS"])
    lt = (line_type or "").upper()
    if lt == "OVERAGE":
        return dict(GOLDEN_TAX_GOODS_CATALOG_V1["API_METERING_OVERAGE"])
    if lt == "COMMIT_TOPUP":
        return dict(GOLDEN_TAX_GOODS_CATALOG_V1["CONTRACT_MIN_COMMIT_TOPUP"])
    return dict(GOLDEN_TAX_GOODS_CATALOG_V1["SAAS_SUBSCRIPTION"])


def split_golden_tax_paper_limit_v1(amount_cents: int, single_sheet_limit_cents: int = 10_000_000) -> List[int]:
    """2023 百旺金税盘单张纸质专票十万元限额自动拆单工具。"""
    if amount_cents <= 0:
        return []
    lim = max(100_000, int(single_sheet_limit_cents))
    chunks: List[int] = []
    rem = int(amount_cents)
    while rem > 0:
        take = min(rem, lim)
        chunks.append(take)
        rem -= take
    return chunks
