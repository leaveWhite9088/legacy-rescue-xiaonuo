# -*- coding: utf-8 -*-
"""多收单通道（微信企付 / 支付宝企业码 / 银联对公 B2B / 线下银企直联电汇）费率寻优与单笔限额路由器。"""
from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass(frozen=True)
class AcquiringChannelSpec:
    channel_code: str
    display_name: str
    mdr_rate_bps: int          # 比例手续费（基点）
    fixed_fee_cents: int       # 固定按笔手续费（分），大于 0 时优先按封顶计费
    cap_fee_cents: int         # 单笔手续费封顶（分，0 表示不封顶）
    min_tx_cents: int
    max_tx_cents: int
    settlement_lag_days: int   # T+N 资金清算到账天数
    healthy: bool = True


CHANNELS: Dict[str, AcquiringChannelSpec] = {
    "WECHAT_NATIVE_V2": AcquiringChannelSpec("WECHAT_NATIVE_V2", "微信支付企业扫码", 60, 0, 0, 100, 5_000_000, 1),
    "ALIPAY_CORP_QR": AcquiringChannelSpec("ALIPAY_CORP_QR", "支付宝当面付企业版", 55, 0, 0, 100, 10_000_000, 1),
    "UNIONPAY_B2B_GATEWAY": AcquiringChannelSpec("UNIONPAY_B2B_GATEWAY", "银联企业网银 B2B", 15, 800, 2_500, 10_000, 500_000_000, 1),
    "BANK_WIRE_VIRTUAL_ACCT": AcquiringChannelSpec("BANK_WIRE_VIRTUAL_ACCT", "对公专属虚拟子账户电汇", 0, 200, 200, 50_000, 2_000_000_000, 0),
}


def estimate_channel_acquiring_fee_cents(spec: AcquiringChannelSpec, amount_cents: int) -> int:
    amt = max(0, int(amount_cents))
    if spec.mdr_rate_bps == 0:
        return spec.fixed_fee_cents
    prop_fee = int(round((amt * spec.mdr_rate_bps) / 10000.0)) + spec.fixed_fee_cents
    if spec.cap_fee_cents > 0:
        return min(prop_fee, spec.cap_fee_cents)
    return prop_fee


def select_optimal_acquiring_channel(
    amount_cents: int,
    prefer_instant_settlement: bool = False,
    disabled_channels: List[str] = None,
) -> Dict[str, Any]:
    """根据充值/收款金额选择综合通道成本最低且满足限额约束的收单渠道。"""
    amt = max(0, int(amount_cents))
    blocked = set(disabled_channels or [])
    eligible: List[Dict[str, Any]] = []

    for code, spec in CHANNELS.items():
        if not spec.healthy or code in blocked:
            continue
        if amt < spec.min_tx_cents or amt > spec.max_tx_cents:
            continue
        fee = estimate_channel_acquiring_fee_cents(spec, amt)
        # 若要求实时到账，对 T+1 渠道施加虚拟时间机会成本权重用于排序
        score = fee + (spec.settlement_lag_days * 500 if prefer_instant_settlement else 0)
        eligible.append({
            "channel_code": code,
            "display_name": spec.display_name,
            "estimated_fee_cents": fee,
            "net_proceeds_cents": max(0, amt - fee),
            "settlement_lag_days": spec.settlement_lag_days,
            "routing_score": score,
        })

    if not eligible:
        return {
            "routed": False,
            "reason": "NO_ELIGIBLE_CHANNEL_FOR_AMOUNT",
            "amount_cents": amt,
            "recommended": None,
            "alternatives": [],
        }

    ordered = sorted(eligible, key=lambda x: (x["routing_score"], x["estimated_fee_cents"], x["channel_code"]))
    return {
        "routed": True,
        "amount_cents": amt,
        "recommended": ordered[0],
        "alternatives": ordered[1:],
    }
