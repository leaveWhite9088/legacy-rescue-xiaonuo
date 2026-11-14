# -*- coding: utf-8 -*-
"""招商银行企业财资管理云（CMB CBS 银企直联）`SDKPGK` XML 电子回单查询报文组装与响应解析器。"""
import xml.etree.ElementTree as ET
import xml.sax.saxutils as saxutils
from typing import Any, Dict, List


def _esc(v: Any) -> str:
    return saxutils.escape("" if v is None else str(v))


def build_cmb_cbs_query_trans_xml(
    login_name: str,
    bank_branch_no: str,
    corp_account_no: str,
    begin_ymd_compact: str,
    end_ymd_compact: str,
) -> str:
    """生成招行银企直联 `GetTransInfo` 当日/历史账户收支明细查询 XML。"""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<CMBSDKPGK>\n'
        '  <INFO>\n'
        '    <FUNNAM>GetTransInfo</FUNNAM>\n'
        '    <DATTYP>2</DATTYP>\n'
        f'    <LGNNAM>{_esc(login_name)}</LGNNAM>\n'
        '  </INFO>\n'
        '  <SDKTSINFX>\n'
        f'    <BBKNBR>{_esc(bank_branch_no)}</BBKNBR>\n'
        f'    <ACCNBR>{_esc(corp_account_no)}</ACCNBR>\n'
        f'    <BGNDAT>{_esc(begin_ymd_compact)}</BGNDAT>\n'
        f'    <ENDDAT>{_esc(end_ymd_compact)}</ENDDAT>\n'
        '    <LOWAMT>0.01</LOWAMT>\n'
        '  </SDKTSINFX>\n'
        '</CMBSDKPGK>'
    )


def parse_cmb_cbs_trans_response_xml(raw_xml: str) -> Dict[str, Any]:
    if not (raw_xml or "").strip():
        return {"ret_code": "-1", "err_msg": "EMPTY_XML", "credit_transactions": []}

    root = ET.fromstring(raw_xml.strip())
    info = root.find("INFO")
    ret_code = info.findtext("RETCOD", default="-9") if info is not None else "-9"
    err_msg = info.findtext("ERRMSG", default="") if info is not None else ""

    credits: List[Dict[str, Any]] = []
    for row in root.findall("NTQTSINFZ"):
        amt_dir = (row.findtext("AMTCDR") or "C").strip().upper()
        if amt_dir != "C":
            continue
        amt_txt = (row.findtext("TRSAMT") or "0.00").strip()
        w, _, f = amt_txt.partition(".")
        cents = int(w or "0") * 100 + int((f + "00")[:2])
        credits.append({
            "bank_serial_no": row.findtext("REQNBR", default=""),
            "tx_date": row.findtext("ETYDAT", default=""),
            "payer_name": row.findtext("RPYNAM", default=""),
            "payer_account": row.findtext("RPYACC", default=""),
            "amount_cents": cents,
            "narrative": row.findtext("NARYUR", default=""),
        })

    return {
        "ret_code": ret_code,
        "ok": ret_code == "0",
        "err_msg": err_msg,
        "credit_count": len(credits),
        "total_credit_cents": sum(x["amount_cents"] for x in credits),
        "credit_transactions": credits,
    }
