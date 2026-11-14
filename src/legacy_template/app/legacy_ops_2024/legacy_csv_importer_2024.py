# -*- coding: utf-8 -*-
"""2024 线下银行回单与网关离线话单 CSV 批量清洗导入器。
支持工行 (ICBC)、招行 (CMB)、建行 (CCB)、中行 (BOC) 四大行对公网银导出表头别名映射与重放哈希去重。
"""
import csv
import hashlib
import io
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


BANK_HEADER_ALIASES: Dict[str, Tuple[str, ...]] = {
    "statement_ref": ("流水号", "银行流水号", "交易流水号", "bank_ref", "tx_serial_no", "凭证号"),
    "payer_name": ("对方户名", "付款人名称", "汇款单位", "payer_name", "counterparty_name"),
    "payer_account": ("对方账号", "付款账号", "payer_account", "counterparty_acct"),
    "amount_yuan": ("贷方发生额", "收入金额", "转入金额", "交易金额", "amount", "credit_amount"),
    "tx_date": ("交易日期", "入账日期", "记账日期", "tx_date", "booking_date"),
    "memo": ("摘要", "附言", "用途", "备注", "memo", "remark", "narrative"),
}


@dataclass
class NormalizedBankRow:
    row_number: int
    statement_ref: str
    payer_name: str
    payer_account_masked: str
    amount_cents: int
    tx_date: str
    memo: str
    inferred_tenant_hint: Optional[str]
    dedup_sha256: str


def _strip_bom_and_whitespace(raw_text: str) -> str:
    if not raw_text:
        return ""
    cleaned = raw_text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.strip() for ln in cleaned.split("\n") if ln.strip() and not ln.strip().startswith("#")]
    return "\n".join(lines)


def _resolve_column_mapping(headers: List[str]) -> Dict[str, str]:
    normalized_headers = {h.strip().lower(): h for h in headers if h}
    resolved: Dict[str, str] = {}
    for canonical, aliases in BANK_HEADER_ALIASES.items():
        for alias in aliases:
            key = alias.strip().lower()
            if key in normalized_headers:
                resolved[canonical] = normalized_headers[key]
                break
    return resolved


def _parse_yuan_str_to_cents_2024(raw_val: str) -> int:
    """2024 版金额字符串转分：支持千分位逗号、人民币符号前缀及正负号。"""
    txt = (raw_val or "").strip().replace(",", "").replace("¥", "").replace("￥", "").replace("RMB", "").strip()
    if not txt or txt in ("-", "--", "0", "0.0", "0.00"):
        return 0
    sign = -1 if txt.startswith("-") else 1
    if txt[0] in ("+", "-"):
        txt = txt[1:].strip()
    if "." in txt:
        whole_part, frac_part = txt.split(".", 1)
        frac_2 = (frac_part + "00")[:2]
        cents = int(whole_part or "0") * 100 + int(frac_2)
    else:
        cents = int(txt) * 100
    return sign * cents


def _mask_bank_account(acct: str) -> str:
    digits = "".join(ch for ch in (acct or "") if ch.isdigit())
    if len(digits) <= 8:
        return digits
    return f"{digits[:4]}****{digits[-4:]}"


def _extract_tenant_hint_from_memo(memo: str) -> Optional[str]:
    """从银行附言中提取类似 t_001 或 T-015 的租户编号线索。"""
    text = (memo or "").strip()
    if not text:
        return None
    lower = text.lower().replace("tenant:", " ").replace("租户", " ")
    for token in lower.replace(",", " ").replace(";", " ").replace("：", " ").split():
        cleaned = token.strip("()[]【】")
        if cleaned.startswith("t_") and len(cleaned) >= 4 and cleaned[2:].isdigit():
            return cleaned
        if cleaned.startswith("t-") and len(cleaned) >= 4 and cleaned[2:].isdigit():
            return "t_" + cleaned[2:]
    return None


def parse_multibank_statement_csv_2024(raw_csv: str) -> Dict[str, Any]:
    """解析四大行导出的对公回单 CSV，返回标准入账结构、重复行告警及格式错误列表。"""
    cleaned = _strip_bom_and_whitespace(raw_csv)
    if not cleaned:
        return {"rows": [], "duplicates_skipped": 0, "errors": ["EMPTY_CSV_INPUT"], "total_credit_cents": 0}

    reader = csv.DictReader(io.StringIO(cleaned))
    if not reader.fieldnames:
        return {"rows": [], "duplicates_skipped": 0, "errors": ["MISSING_HEADER_ROW"], "total_credit_cents": 0}

    col_map = _resolve_column_mapping(list(reader.fieldnames))
    missing = [req for req in ("statement_ref", "payer_name", "amount_yuan") if req not in col_map]
    if missing:
        return {
            "rows": [],
            "duplicates_skipped": 0,
            "errors": [f"UNRECOGNIZED_COLUMNS:{','.join(missing)}"],
            "total_credit_cents": 0,
        }

    seen_hashes = set()
    accepted: List[Dict[str, Any]] = []
    errors: List[str] = []
    dup_count = 0
    total_cents = 0

    for idx, row in enumerate(reader, start=2):
        ref = str(row.get(col_map["statement_ref"]) or "").strip()
        payer = str(row.get(col_map["payer_name"]) or "").strip()
        acct = str(row.get(col_map.get("payer_account", ""), "") or "").strip()
        tx_date = str(row.get(col_map.get("tx_date", ""), "") or "2026-11-01").strip()
        memo = str(row.get(col_map.get("memo", ""), "") or "").strip()
        raw_amt = str(row.get(col_map["amount_yuan"]) or "").strip()

        if not ref or not payer:
            errors.append(f"ROW_{idx}:MISSING_REF_OR_PAYER")
            continue
        try:
            amt_cents = _parse_yuan_str_to_cents_2024(raw_amt)
        except ValueError:
            errors.append(f"ROW_{idx}:INVALID_AMOUNT:{raw_amt}")
            continue

        if amt_cents <= 0:
            # 借方转出或零金额回单不进入收款认领池
            continue

        digest_src = f"{ref}|{payer}|{amt_cents}|{tx_date}".encode("utf-8")
        digest = hashlib.sha256(digest_src).hexdigest()[:24]
        if digest in seen_hashes:
            dup_count += 1
            continue
        seen_hashes.add(digest)

        norm = NormalizedBankRow(
            row_number=idx,
            statement_ref=ref,
            payer_name=payer,
            payer_account_masked=_mask_bank_account(acct),
            amount_cents=amt_cents,
            tx_date=tx_date,
            memo=memo,
            inferred_tenant_hint=_extract_tenant_hint_from_memo(memo),
            dedup_sha256=digest,
        )
        accepted.append(norm.__dict__)
        total_cents += amt_cents

    return {
        "rows": accepted,
        "duplicates_skipped": dup_count,
        "errors": errors,
        "total_credit_cents": total_cents,
        "column_mapping_used": col_map,
    }
