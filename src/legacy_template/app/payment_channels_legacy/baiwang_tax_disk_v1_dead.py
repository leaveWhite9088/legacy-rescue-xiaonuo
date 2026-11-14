# -*- coding: utf-8 -*-
"""2024 百旺金赋税控服务器老接口封装（已于 2025 Q4 切换至金税四期数电乐企通道，本模块停用留档）。"""
from typing import Any, Dict


def issue_paper_special_fapiao_v1_dead(invoice_id: str, gross_cents: int, tax_rate_pct: int = 6) -> Dict[str, Any]:
    net = int(round(gross_cents / (1.0 + tax_rate_pct / 100.0)))
    return {
        "channel": "BAIWANG_DISK_2024_DEAD",
        "invoice_id": invoice_id,
        "paper_code": "3100241130",
        "net_cents": net,
        "tax_cents": gross_cents - net,
        "deprecated": True,
    }
