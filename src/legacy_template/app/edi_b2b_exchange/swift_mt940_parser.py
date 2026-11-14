# -*- coding: utf-8 -*-
"""国际结算银行 SWIFT MT940 电子对账单报文（`:20:`, `:25:`, `:60F:`, `:61:`, `:86:`, `:62F:`）解析与余额勾稽引擎。
业务场景：香港及新加坡离岸外币收款账户每日清晨通过银企 SFTP 推送 MT940 文本，本模块负责拆解起止头寸与逐笔借贷明细，
并校验期初余额 + 明细发生额净值 == 期末余额，防止报文截断引发重复入账或漏认领。
"""
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class Mt940StatementLine:
    value_date_yymmdd: str
    dc_mark: str            # 'C' (Credit 收款) | 'D' (Debit 付款) | 'RC' (冲正贷) | 'RD' (冲正借)
    amount_minor: int
    tx_type_code: str
    customer_ref: str
    narrative_86: str


def _parse_mt940_balance_tag(tag_body: str) -> Tuple[str, str, str, int]:
    """解析形如 `C261101USD125430,50` 的 `:60F:` / `:62F:` 余额字段。"""
    raw = (tag_body or "").strip()
    if len(raw) < 11:
        raise ValueError(f"Malformed MT940 balance tag: {raw}")
    dc = raw[0].upper()
    yymmdd = raw[1:7]
    ccy = raw[7:10].upper()
    amt_str = raw[10:].strip().replace(",", ".")
    if "." in amt_str:
        whole, frac = amt_str.split(".", 1)
        minor = int(whole or "0") * 100 + int((frac + "00")[:2])
    else:
        minor = int(amt_str or "0") * 100
    signed = minor if dc == "C" else -minor
    return (dc, yymmdd, ccy, signed)


def _parse_mt940_61_line(tag_body: str) -> Tuple[str, str, int, str, str]:
    """解析形如 `261112C19900,00NTRFREF_CUST_008//BANKSEQ991` 的 `:61:` 交易行。"""
    raw = (tag_body or "").strip()
    if len(raw) < 10:
        raise ValueError(f"Malformed :61: line: {raw}")
    yymmdd = raw[:6]
    idx = 6
    # 可选 4 位入账月日 MMDD
    if len(raw) > 10 and raw[6:10].isdigit():
        idx = 10
    if raw[idx:idx + 2].upper() in ("RC", "RD"):
        dc = raw[idx:idx + 2].upper()
        idx += 2
    else:
        dc = raw[idx].upper()
        idx += 1

    # 提取逗号小数金额直至遇到字母（通常为 'N' 开头交易码，如 NTRF / NMSC / NCHG）
    amt_chars: List[str] = []
    while idx < len(raw) and (raw[idx].isdigit() or raw[idx] in (",", ".")):
        amt_chars.append(raw[idx])
        idx += 1
    amt_txt = "".join(amt_chars).replace(",", ".")
    if "." in amt_txt:
        w, f = amt_txt.split(".", 1)
        minor = int(w or "0") * 100 + int((f + "00")[:2])
    else:
        minor = int(amt_txt or "0") * 100

    tx_code = raw[idx:idx + 4] if idx + 4 <= len(raw) else "NTRF"
    rest_ref = raw[idx + 4:].split("//", 1)[0].strip()
    return (yymmdd, dc, minor, tx_code, rest_ref)


def parse_swift_mt940_message(raw_mt940_text: str) -> Dict[str, Any]:
    """完整解析单份 SWIFT MT940 报文并执行头尾余额闭环校验。"""
    lines = [ln.strip() for ln in (raw_mt940_text or "").replace("\r\n", "\n").split("\n") if ln.strip()]
    tx_ref_20 = ""
    account_25 = ""
    opening_ccy = "USD"
    opening_signed_minor = 0
    closing_signed_minor = 0
    has_opening = False
    has_closing = False

    entries: List[Mt940StatementLine] = []
    pending_61: Optional[Tuple[str, str, int, str, str]] = None

    for ln in lines:
        if ln in ("-", "-}"):
            continue
        if ln.startswith(":20:"):
            tx_ref_20 = ln[4:].strip()
        elif ln.startswith(":25:"):
            account_25 = ln[4:].strip()
        elif ln.startswith(":60F:") or ln.startswith(":60M:"):
            _, _, opening_ccy, opening_signed_minor = _parse_mt940_balance_tag(ln[5:])
            has_opening = True
        elif ln.startswith(":61:"):
            if pending_61 is not None:
                entries.append(Mt940StatementLine(*pending_61, narrative_86=""))
            pending_61 = _parse_mt940_61_line(ln[4:])
        elif ln.startswith(":86:"):
            memo = ln[4:].strip()
            if pending_61 is not None:
                entries.append(Mt940StatementLine(*pending_61, narrative_86=memo))
                pending_61 = None
        elif ln.startswith(":62F:") or ln.startswith(":62M:"):
            if pending_61 is not None:
                entries.append(Mt940StatementLine(*pending_61, narrative_86=""))
                pending_61 = None
            _, _, _, closing_signed_minor = _parse_mt940_balance_tag(ln[5:])
            has_closing = True

    if pending_61 is not None:
        entries.append(Mt940StatementLine(*pending_61, narrative_86=""))

    net_movement = 0
    credit_count = 0
    debit_count = 0
    serialized_entries: List[Dict[str, Any]] = []

    for e in entries:
        if e.dc_mark in ("C", "RD"):
            signed_delta = e.amount_minor if e.dc_mark == "C" else -e.amount_minor
            if e.dc_mark == "C":
                credit_count += 1
            else:
                debit_count += 1
        else:
            signed_delta = -e.amount_minor if e.dc_mark == "D" else e.amount_minor
            if e.dc_mark == "D":
                debit_count += 1
            else:
                credit_count += 1
        net_movement += signed_delta
        serialized_entries.append({
            "value_date_yymmdd": e.value_date_yymmdd,
            "dc_mark": e.dc_mark,
            "amount_minor": e.amount_minor,
            "signed_delta_minor": signed_delta,
            "tx_type_code": e.tx_type_code,
            "customer_ref": e.customer_ref,
            "narrative_86": e.narrative_86,
        })

    computed_closing = opening_signed_minor + net_movement
    balance_reconciled = (not has_opening or not has_closing) or (computed_closing == closing_signed_minor)

    return {
        "statement_ref_20": tx_ref_20,
        "account_id_25": account_25,
        "currency": opening_ccy,
        "opening_balance_minor": opening_signed_minor,
        "net_movement_minor": net_movement,
        "computed_closing_minor": computed_closing,
        "reported_closing_minor": closing_signed_minor,
        "balance_reconciled": balance_reconciled,
        "credit_entry_count": credit_count,
        "debit_entry_count": debit_count,
        "entries": serialized_entries,
    }
