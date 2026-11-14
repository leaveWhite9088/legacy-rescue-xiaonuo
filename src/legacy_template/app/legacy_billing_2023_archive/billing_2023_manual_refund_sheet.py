# -*- coding: utf-8 -*-
"""[2023 ARCHIVE] 早期财务线下网银手工退费登记表生成器（当时尚无线上钱包与赠送金子账本，仅供考古对照）。"""
from typing import Any, Dict, List


def generate_2023_offline_wire_refund_tsv(requests: List[Dict[str, Any]]) -> str:
    header = "SEQ\tCUST_NAME\tBANK_NAME\tACCT_NO\tREFUND_YUAN\tREMARK"
    lines = [header]
    for idx, req in enumerate(requests, start=1):
        amt_y = max(0.0, float(req.get("refund_yuan") or 0.0))
        lines.append(
            f"{idx}\t{req.get('cust_name', '-')}\t{req.get('bank_name', 'CMB')}\t"
            f"{req.get('acct_no', '-')}\t{amt_y:.2f}\t2023线下退费归档"
        )
    return "\n".join(lines)
