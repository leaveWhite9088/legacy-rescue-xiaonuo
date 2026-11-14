# -*- coding: utf-8 -*-
"""2025 多品牌企业 ERP 财务对账单双向桥接导出器（支持 SAP FI / NetSuite / 金蝶云星空 / 用友 BIP 四种列布局）。"""
import csv
import io
from typing import Any, Dict, List


ERP_LAYOUT_COLUMNS: Dict[str, List[str]] = {
    "KINGDEE_CLOUD": ["FBillNo", "FCustId", "FPeriod", "FPlanCode", "FPreTaxAmt", "FTaxAmt", "FTotalAmt", "FStatus"],
    "YONGYOU_BIP": ["vbillcode", "pk_customer", "accperiod", "plan_code", "nmny", "ntax", "ntotalmny", "fstatusflag"],
    "SAP_FI": ["BELNR", "KUNNR", "MONAT", "MATNR", "NETWR", "MWSBP", "WRBTR", "BSTAT"],
    "NETSUITE": ["tranId", "entity", "postingPeriod", "item", "subtotal", "taxTotal", "total", "status"],
}


def export_invoices_for_target_erp(invoices: List[Dict[str, Any]], erp_dialect: str = "KINGDEE_CLOUD") -> str:
    dialect = (erp_dialect or "KINGDEE_CLOUD").upper()
    cols = ERP_LAYOUT_COLUMNS.get(dialect, ERP_LAYOUT_COLUMNS["KINGDEE_CLOUD"])

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(cols)

    for inv in invoices:
        tot = int(inv.get("total_cents") or 0)
        tax = int(inv.get("tax_cents") or 0)
        pretax = tot - tax
        writer.writerow([
            inv.get("id", ""),
            inv.get("tenant_id", ""),
            inv.get("period_key", ""),
            inv.get("plan_code", ""),
            f"{pretax / 100.0:.2f}",
            f"{tax / 100.0:.2f}",
            f"{tot / 100.0:.2f}",
            inv.get("status", ""),
        ])
    return buf.getvalue()
