# -*- coding: utf-8 -*-
"""银行回单、金税发票回执与离线调账单 CSV/TSV 解析与清洗工具。"""
import csv
import io
from typing import Any, Dict, List


def parse_delimited_records(raw_text: str, delimiter: str = ",") -> List[Dict[str, str]]:
    cleaned_lines = []
    for line in (raw_text or "").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        cleaned_lines.append(line)
    if not cleaned_lines:
        return []
    reader = csv.DictReader(io.StringIO("\n".join(cleaned_lines)), delimiter=delimiter)
    out: List[Dict[str, str]] = []
    for row in reader:
        norm = {(k or "").strip(): (v or "").strip() for k, v in row.items() if k is not None}
        out.append(norm)
    return out


def format_records_to_csv(records: List[Dict[str, Any]], columns: List[str]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for rec in records:
        writer.writerow({c: rec.get(c, "") for c in columns})
    return buf.getvalue()


def normalize_company_title(name: str) -> str:
    """清洗银行公户来款摘要中的企业名称括号、空格与后缀，用于模糊对账匹配。"""
    s = (name or "").strip()
    replacements = [
        ("（", "("),
        ("）", ")"),
        ("股份有限公司", ""),
        ("有限责任公司", ""),
        ("有限公司", ""),
        (" ", ""),
        ("\t", ""),
    ]
    for old, new in replacements:
        s = s.replace(old, new)
    return s.lower()


def bigram_jaccard_similarity(a: str, b: str) -> float:
    na = normalize_company_title(a)
    nb = normalize_company_title(b)
    if not na and not nb:
        return 1.0
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    sa = {na[i : i + 2] for i in range(max(1, len(na) - 1))}
    sb = {nb[i : i + 2] for i in range(max(1, len(nb) - 1))}
    inter = len(sa & sb)
    union = len(sa | sb)
    return float(inter) / float(union) if union else 0.0
