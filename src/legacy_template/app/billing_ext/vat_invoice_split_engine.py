# -*- coding: utf-8 -*-
"""金税四期数电专票超限额自动拆票（Sheet Splitting）与尾差守恒引擎。
税务实务背景：部分企业租户单张数电专票开票授信单笔上限为人民币 100,000.00 元（10,000,000 分）；
当月度大客户账单含税总额超过单张限额时，需拆分为 N 张子发票，且所有子票的【不含税金额之和】与【税额之和】必须与原账单分毫不差。
"""
import math
from typing import Any, Dict, List

from app.infra.config import FAPIAO_SINGLE_SHEET_MAX_CENTS


def plan_fapiao_sheet_splits(
    invoice_id: str,
    gross_total_cents: int,
    vat_rate_bps: int = 600,
    max_sheet_gross_cents: int = FAPIAO_SINGLE_SHEET_MAX_CENTS,
) -> Dict[str, Any]:
    gross = max(0, int(gross_total_cents))
    limit = max(10_000, int(max_sheet_gross_cents))
    rate = max(0, int(vat_rate_bps))

    total_net = int(round((gross * 10000.0) / (10000.0 + rate))) if rate > 0 else gross
    total_tax = gross - total_net

    if gross == 0:
        return {
            "invoice_id": invoice_id,
            "sheet_count": 0,
            "total_net_cents": 0,
            "total_tax_cents": 0,
            "total_gross_cents": 0,
            "sheets": [],
        }

    num_sheets = int(math.ceil(gross / float(limit)))
    sheets: List[Dict[str, Any]] = []
    rem_gross = gross
    alloc_net = 0
    alloc_tax = 0

    for idx in range(1, num_sheets + 1):
        if idx < num_sheets:
            sh_gross = min(limit, rem_gross)
            sh_net = int(round((sh_gross * 10000.0) / (10000.0 + rate))) if rate > 0 else sh_gross
            sh_tax = sh_gross - sh_net
            alloc_net += sh_net
            alloc_tax += sh_tax
            rem_gross -= sh_gross
        else:
            sh_gross = rem_gross
            sh_net = total_net - alloc_net
            sh_tax = total_tax - alloc_tax
            rem_gross = 0

        sheets.append({
            "sheet_seq": idx,
            "sub_fapiao_ref": f"{invoice_id}-S{idx:02d}",
            "net_cents": sh_net,
            "tax_cents": sh_tax,
            "gross_cents": sh_gross,
        })

    return {
        "invoice_id": invoice_id,
        "sheet_count": len(sheets),
        "single_sheet_ceiling_cents": limit,
        "total_net_cents": total_net,
        "total_tax_cents": total_tax,
        "total_gross_cents": gross,
        "penny_conserved": (
            sum(s["net_cents"] for s in sheets) == total_net
            and sum(s["tax_cents"] for s in sheets) == total_tax
            and sum(s["gross_cents"] for s in sheets) == gross
        ),
        "sheets": sheets,
    }
