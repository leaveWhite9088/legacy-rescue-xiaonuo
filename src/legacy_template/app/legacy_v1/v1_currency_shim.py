# -*- coding: utf-8 -*-
"""2024 v1 历史金额格式转换与多币种汇率折算遗留工具。
注：parse_v1_yuan_string 仍被 app.infra.db 与对账模块用于解析 YUAN_STR 历史账单。
其余港币/美元折算与旧版四舍五入函数为 2024 跨境试点遗留代码。
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, ROUND_HALF_UP
import re
from typing import Any, Dict, List, Optional, Tuple

V1_STATIC_FX_TABLE_2024: Dict[str, Tuple[int, int]] = {
    "CNY": (10000, 10000),
    "RMB": (10000, 10000),
    "HKD": (9215, 10000),
    "USD": (71850, 10000),
    "SGD": (53620, 10000),
    "JPY": (482, 10000),
    "EUR": (78120, 10000),
}

_CURRENCY_PREFIX_RE = re.compile(r"^[¥￥$€£]|^(RMB|CNY|HKD|USD|SGD)\s*", re.IGNORECASE)
_THOUSAND_SEP_RE = re.compile(r",(?=\d{3}(\D|$))")


def parse_v1_yuan_string(raw_val: Any, fallback_cents: int = 0) -> int:
    """将 2024 v1 遗留账单中的元单位字符串（如 '89.10'、'¥1,299.00'、'99'）安全解析为整数分。"""
    if raw_val is None:
        return int(fallback_cents)
    if isinstance(raw_val, bool):
        return int(fallback_cents)
    if isinstance(raw_val, int):
        return raw_val * 100
    s = str(raw_val).strip()
    if not s:
        return int(fallback_cents)
    s = _CURRENCY_PREFIX_RE.sub("", s).strip()
    s = _THOUSAND_SEP_RE.sub("", s)
    try:
        dec = Decimal(s)
        cents = int((dec * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        return cents
    except (InvalidOperation, ValueError):
        return int(fallback_cents)


def format_v1_yuan_display(cents: int, with_symbol: bool = True, thousand_sep: bool = False) -> str:
    """将整数分格式化为 v1 兼容元字符串。"""
    neg = cents < 0
    abs_c = abs(int(cents))
    yuan = abs_c // 100
    rem = abs_c % 100
    yuan_str = f"{yuan:,}" if thousand_sep else str(yuan)
    prefix = "-" if neg else ""
    sym = "¥" if with_symbol else ""
    return f"{prefix}{sym}{yuan_str}.{rem:02d}"


def convert_v1_foreign_to_cny_cents(
    foreign_minor_units: int,
    currency_code: str,
    custom_rate_bps: Optional[int] = None,
) -> Dict[str, Any]:
    """2024 Q2 离岸结算试点折算函数（现已停用实时拉取，保留静态兜底供历史审计单查询）。"""
    code = (currency_code or "CNY").upper().strip()
    if custom_rate_bps is not None and custom_rate_bps > 0:
        num, den = int(custom_rate_bps), 10000
    else:
        num, den = V1_STATIC_FX_TABLE_2024.get(code, (10000, 10000))

    if code == "JPY":
        # 日元无辅币分单位，按百日元基数折算
        cny_cents = (int(foreign_minor_units) * 100 * num + den // 2) // den
    else:
        cny_cents = (int(foreign_minor_units) * num + den // 2) // den

    return {
        "source_currency": code,
        "source_minor_units": int(foreign_minor_units),
        "applied_rate_num": num,
        "applied_rate_den": den,
        "cny_cents": cny_cents,
    }


def v1_bankers_round_tax_split(gross_cents: int, tax_rate_pct: float) -> Dict[str, int]:
    """旧版银行家舍入价内税拆分（注意：2025 v2 已改用 app.domain.tax_engine 标准四舍五入）。"""
    if gross_cents <= 0 or tax_rate_pct <= 0:
        return {"net_cents": max(0, int(gross_cents)), "tax_cents": 0, "gross_cents": max(0, int(gross_cents))}
    gross_dec = Decimal(int(gross_cents))
    divisor = Decimal("1") + (Decimal(str(tax_rate_pct)) / Decimal("100"))
    net_dec = (gross_dec / divisor).quantize(Decimal("1"), rounding=ROUND_HALF_EVEN)
    net_c = int(net_dec)
    return {
        "net_cents": net_c,
        "tax_cents": int(gross_cents) - net_c,
        "gross_cents": int(gross_cents),
    }


def reconcile_v1_csv_money_column(rows: List[Dict[str, Any]], col_name: str = "amount_yuan") -> Dict[str, Any]:
    """解析早期线下手工导入台账中的混合金额列，输出汇总及异常行号。"""
    total_cents = 0
    malformed: List[int] = []
    parsed_values: List[int] = []
    for idx, row in enumerate(rows):
        raw = row.get(col_name)
        if raw is None or str(raw).strip() == "":
            malformed.append(idx)
            continue
        sentinel = -999999999
        val = parse_v1_yuan_string(raw, fallback_cents=sentinel)
        if val == sentinel:
            malformed.append(idx)
            continue
        total_cents += val
        parsed_values.append(val)

    return {
        "row_count": len(rows),
        "valid_count": len(parsed_values),
        "malformed_indices": malformed,
        "total_cents": total_cents,
        "min_cents": min(parsed_values) if parsed_values else 0,
        "max_cents": max(parsed_values) if parsed_values else 0,
    }


def split_installment_schedule_v1(total_cents: int, months: int, front_load_remainder: bool = True) -> List[Dict[str, int]]:
    """2024 年付分期摊销计划生成器（供老版预收账款递延摊销脚本使用）。"""
    if months <= 0:
        raise ValueError("months must be positive")
    base = int(total_cents) // months
    rem = int(total_cents) - base * months
    schedule: List[Dict[str, int]] = []
    acc = 0
    for idx in range(1, months + 1):
        amt = base
        if front_load_remainder and idx == 1:
            amt += rem
        elif not front_load_remainder and idx == months:
            amt += rem
        acc += amt
        schedule.append({
            "installment_no": idx,
            "amount_cents": amt,
            "cumulative_cents": acc,
            "remaining_cents": int(total_cents) - acc,
        })
    return schedule


def legacy_cent_checksum(tenant_id: str, period_key: str, total_cents: int) -> str:
    """生成 2024 纸质盖章对账单底部的 8 位校验码。"""
    seed = f"{tenant_id}|{period_key}|{int(total_cents)}|YC2024"
    acc = 0x811C9DC5
    for ch in seed.encode("utf-8"):
        acc ^= ch
        acc = (acc * 0x01000193) & 0xFFFFFFFF
    return f"V1CHK-{acc:08X}"
