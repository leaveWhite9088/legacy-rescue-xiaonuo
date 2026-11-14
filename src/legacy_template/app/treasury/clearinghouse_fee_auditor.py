# -*- coding: utf-8 -*-
"""第三方支付清算机构（微信/支付宝/银联）日终结算单手续费扣率核对器。"""
from typing import Any, Dict, List

from app.treasury.payment_channel_router import CHANNELS, estimate_channel_acquiring_fee_cents


def audit_clearinghouse_settlement_batch(settlement_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """核对收单机构实际扣收手续费与合同约定 MDR 费率是否存在超扣偏差（容忍 1 分钱四舍五入差）。"""
    total_gross = 0
    total_actual_fee = 0
    total_expected_fee = 0
    discrepancies: List[Dict[str, Any]] = []

    for idx, row in enumerate(settlement_rows, start=1):
        ch_code = str(row.get("channel_code") or "WECHAT_NATIVE_V2")
        gross = max(0, int(row.get("gross_cents") or 0))
        actual_fee = max(0, int(row.get("charged_fee_cents") or 0))
        spec = CHANNELS.get(ch_code, CHANNELS["WECHAT_NATIVE_V2"])
        expected_fee = estimate_channel_acquiring_fee_cents(spec, gross)

        total_gross += gross
        total_actual_fee += actual_fee
        total_expected_fee += expected_fee

        if abs(actual_fee - expected_fee) > 1:
            discrepancies.append({
                "line_index": idx,
                "tx_ref": row.get("tx_ref", f"TX-{idx}"),
                "channel_code": ch_code,
                "gross_cents": gross,
                "expected_fee_cents": expected_fee,
                "charged_fee_cents": actual_fee,
                "overcharged_cents": actual_fee - expected_fee,
            })

    return {
        "checked_count": len(settlement_rows),
        "total_gross_cents": total_gross,
        "total_expected_fee_cents": total_expected_fee,
        "total_charged_fee_cents": total_actual_fee,
        "net_settlement_cents": total_gross - total_actual_fee,
        "discrepancy_count": len(discrepancies),
        "discrepancies": discrepancies,
    }
