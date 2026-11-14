# -*- coding: utf-8 -*-
"""2024 金税三期向数电票（金税四期）切换期间的价税分离尾差（Penny Rounding）调平算法。"""
from typing import Any, Dict, List


def reconcile_line_item_vat_penny_diff(
    line_items_gross_cents: List[int],
    vat_rate_bps: int = 600,
    inclusive: bool = True,
) -> Dict[str, Any]:
    """逐行价税分离与整单合计价税分离存在 1~2 分钱四舍五入尾差时，将尾差吸收至最大金额明细行。"""
    clean_items = [max(0, int(x)) for x in line_items_gross_cents]
    if not clean_items:
        return {"lines": [], "invoice_net_cents": 0, "invoice_tax_cents": 0, "invoice_gross_cents": 0, "penny_adjusted_cents": 0}

    rate = max(0, int(vat_rate_bps))
    if inclusive:
        total_gross = sum(clean_items)
        target_net = int(round((total_gross * 10000.0) / (10000 + rate)))
        target_tax = total_gross - target_net

        lines: List[Dict[str, int]] = []
        for idx, g_cents in enumerate(clean_items):
            ln_net = int(round((g_cents * 10000.0) / (10000 + rate)))
            ln_tax = g_cents - ln_net
            lines.append({"line_no": idx + 1, "net_cents": ln_net, "tax_cents": ln_tax, "gross_cents": g_cents})

        sum_line_tax = sum(l["tax_cents"] for l in lines)
        diff = target_tax - sum_line_tax
        if diff != 0:
            max_line = max(lines, key=lambda x: x["gross_cents"])
            max_line["tax_cents"] += diff
            max_line["net_cents"] -= diff

        return {
            "lines": lines,
            "invoice_net_cents": target_net,
            "invoice_tax_cents": target_tax,
            "invoice_gross_cents": total_gross,
            "penny_adjusted_cents": diff,
        }
    else:
        total_net = sum(clean_items)
        target_tax = int(round((total_net * rate) / 10000.0))
        total_gross = total_net + target_tax

        lines = []
        for idx, n_cents in enumerate(clean_items):
            ln_tax = int(round((n_cents * rate) / 10000.0))
            lines.append({"line_no": idx + 1, "net_cents": n_cents, "tax_cents": ln_tax, "gross_cents": n_cents + ln_tax})

        sum_line_tax = sum(l["tax_cents"] for l in lines)
        diff = target_tax - sum_line_tax
        if diff != 0:
            max_line = max(lines, key=lambda x: x["net_cents"])
            max_line["tax_cents"] += diff
            max_line["gross_cents"] += diff

        return {
            "lines": lines,
            "invoice_net_cents": total_net,
            "invoice_tax_cents": target_tax,
            "invoice_gross_cents": total_gross,
            "penny_adjusted_cents": diff,
        }
