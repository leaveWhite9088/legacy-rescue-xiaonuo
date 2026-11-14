# -*- coding: utf-8 -*-
"""2024 V1 遗留：零外部依赖 PDF-1.4 简易英文商业催款回执字节流生成器（供无 headless 浏览器环境下的归档导出）。"""
from typing import Any, Dict, List


def _escape_pdf_text(text: str) -> str:
    ascii_safe = "".join(ch if 32 <= ord(ch) <= 126 else "?" for ch in (text or ""))
    return ascii_safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_minimal_invoice_pdf14_bytes(invoice: Dict[str, Any], tenant_code: str) -> bytes:
    """按 PDF 1.4 交叉引用表（xref）规范拼装单页标准矢量文本账单摘要。"""
    inv_id = str(invoice.get("id") or "INV-NA")
    period = str(invoice.get("period_key") or "2026-11")
    plan = str(invoice.get("plan_code") or "STARTER")
    base_y = int(invoice.get("base_fee_cents") or 0) / 100.0
    ov_y = int(invoice.get("overage_fee_cents") or 0) / 100.0
    tax_y = int(invoice.get("tax_cents") or 0) / 100.0
    tot_y = int(invoice.get("total_cents") or 0) / 100.0
    status = str(invoice.get("status") or "OPEN")

    lines = [
        "YUNCE CLOUD ENTERPRISE BILLING - ARCHIVE RECEIPT",
        f"Invoice No : {inv_id}",
        f"Tenant ID  : {tenant_code}",
        f"Period     : {period}    Plan : {plan}    Status : {status}",
        "------------------------------------------------------------",
        f"Base Subscription Fee : RMB {base_y:10.2f}",
        f"Tiered Overage Fee    : RMB {ov_y:10.2f}",
        f"VAT / Tax Surcharge   : RMB {tax_y:10.2f}",
        "------------------------------------------------------------",
        f"TOTAL AMOUNT DUE      : RMB {tot_y:10.2f}",
    ]

    stream_cmds: List[str] = ["BT", "/F1 11 Tf", "50 760 Td", "16 TL"]
    for idx, ln in enumerate(lines):
        esc = _escape_pdf_text(ln)
        if idx == 0:
            stream_cmds.append(f"({esc}) Tj")
        else:
            stream_cmds.append(f"T* ({esc}) Tj")
    stream_cmds.append("ET")
    stream_body = "\n".join(stream_cmds).encode("latin-1")

    objects: List[bytes] = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n",
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>\nendobj\n",
        f"5 0 obj\n<< /Length {len(stream_body)} >>\nstream\n".encode("latin-1") + stream_body + b"\nendstream\nendobj\n",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets: List[int] = [0]
    for obj in objects:
        offsets.append(len(out))
        out.extend(obj)

    xref_pos = len(out)
    out.extend(f"xref\n0 {len(offsets)}\n".encode("latin-1"))
    out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode("latin-1"))

    out.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode("latin-1")
    )
    return bytes(out)
