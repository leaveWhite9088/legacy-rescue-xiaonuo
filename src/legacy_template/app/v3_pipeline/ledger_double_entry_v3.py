# -*- coding: utf-8 -*-
"""v3 内存严格复式记账 T 型账户引擎原型（2026 实验模块，尚未与生产 SQLite wallets 表打通）。
架构设想：未来取代单边增减余额操作，强制每一笔充值、消费、赠金发放、过期与退费都满足借贷必相等。
"""
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class V3PostingLine:
    account_code: str
    side: str  # 'DEBIT' | 'CREDIT'
    amount_cents: int
    memo: str = ""


@dataclass
class V3JournalVoucher:
    voucher_id: str
    tenant_id: str
    business_event: str
    lines: List[V3PostingLine] = field(default_factory=list)

    def validate_balanced(self) -> Tuple[bool, int, int]:
        debits = sum(ln.amount_cents for ln in self.lines if ln.side == "DEBIT")
        credits = sum(ln.amount_cents for ln in self.lines if ln.side == "CREDIT")
        all_pos = all(ln.amount_cents > 0 for ln in self.lines)
        return (all_pos and len(self.lines) >= 2 and debits == credits), debits, credits


class V3DoubleEntryBookkeeper:
    ACCOUNT_NORMAL_SIDE = {
        "1002_BANK_CASH": "DEBIT",
        "1122_TENANT_AR": "DEBIT",
        "2203_TENANT_WALLET_CASH": "CREDIT",
        "2204_TENANT_WALLET_PROMO": "CREDIT",
        "6001_SAAS_REVENUE": "CREDIT",
        "6601_PROMO_EXPENSE": "DEBIT",
    }

    def __init__(self) -> None:
        self._vouchers: List[V3JournalVoucher] = []
        self._debit_totals: Dict[str, int] = {}
        self._credit_totals: Dict[str, int] = {}

    def post_voucher(self, voucher: V3JournalVoucher) -> Dict[str, object]:
        ok, d_sum, c_sum = voucher.validate_balanced()
        if not ok:
            raise ValueError(f"Unbalanced v3 journal voucher {voucher.voucher_id}: debit={d_sum}, credit={c_sum}")
        for ln in voucher.lines:
            if ln.account_code not in self.ACCOUNT_NORMAL_SIDE:
                raise KeyError(f"Unknown v3 ledger account: {ln.account_code}")
            if ln.side == "DEBIT":
                self._debit_totals[ln.account_code] = self._debit_totals.get(ln.account_code, 0) + ln.amount_cents
            else:
                self._credit_totals[ln.account_code] = self._credit_totals.get(ln.account_code, 0) + ln.amount_cents
        self._vouchers.append(voucher)
        return {"voucher_id": voucher.voucher_id, "posted_cents": d_sum}

    def build_trial_balance(self) -> Dict[str, object]:
        accounts = sorted(set(self._debit_totals.keys()) | set(self._credit_totals.keys()))
        rows = []
        grand_debit = 0
        grand_credit = 0
        for acct in accounts:
            d_val = self._debit_totals.get(acct, 0)
            c_val = self._credit_totals.get(acct, 0)
            grand_debit += d_val
            grand_credit += c_val
            normal = self.ACCOUNT_NORMAL_SIDE.get(acct, "DEBIT")
            net = (d_val - c_val) if normal == "DEBIT" else (c_val - d_val)
            rows.append({
                "account_code": acct,
                "normal_side": normal,
                "debit_cents": d_val,
                "credit_cents": c_val,
                "ending_balance_cents": net,
            })
        return {
            "voucher_count": len(self._vouchers),
            "grand_debit_cents": grand_debit,
            "grand_credit_cents": grand_credit,
            "is_balanced": grand_debit == grand_credit,
            "accounts": rows,
        }
