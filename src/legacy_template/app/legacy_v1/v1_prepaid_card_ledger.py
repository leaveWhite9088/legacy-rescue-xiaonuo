# -*- coding: utf-8 -*-
"""2024 V1 遗留：线下展会与算力产业园实体储值点卡（Prepaid Compute Card）卡号生成、Luhn 校验与激活台账模拟器。
历史说明：
- 2024 年销售团队向高校与孵化器发放过面值 ¥500 / ¥2,000 的纸质算力卡（分 `PAID_CASH_CARD` 有偿购卡与 `PROMO_GIFT_CARD` 无偿赠卡两类）；
- 2025 年统一并入 `wallets` 与 `promo_grants` 表后，本模块仅保留卡号校验逻辑供老卡兑付核验，不再直接操作线上钱包表。
"""
from dataclasses import dataclass
from typing import Any, Dict, List


CARD_DENOMINATIONS_CENTS: Dict[str, Dict[str, Any]] = {
    "YC24_CASH_500": {"face_cents": 50_000, "bucket": "CASH", "invoiceable": True, "validity_days": 1095},
    "YC24_CASH_2000": {"face_cents": 200_000, "bucket": "CASH", "invoiceable": True, "validity_days": 1095},
    "YC24_GIFT_200": {"face_cents": 20_000, "bucket": "PROMO", "invoiceable": False, "validity_days": 180},
    "YC24_GIFT_1000": {"face_cents": 100_000, "bucket": "PROMO", "invoiceable": False, "validity_days": 365},
}


@dataclass
class LegacyPrepaidCardRecord:
    card_number: str
    sku_code: str
    face_cents: int
    target_bucket: str
    status: str           # 'ISSUED' | 'REDEEMED' | 'FROZEN' | 'EXPIRED'
    redeemed_by_tenant: str = ""


def compute_luhn_check_digit(digits_without_check: str) -> str:
    clean = "".join(ch for ch in digits_without_check if ch.isdigit())
    if not clean:
        raise ValueError("Empty numeric payload for Luhn check")
    total = 0
    rev = clean[::-1]
    for i, ch in enumerate(rev):
        n = ord(ch) - 48
        if i % 2 == 0:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    check = (10 - (total % 10)) % 10
    return str(check)


def verify_prepaid_card_number(card_number: str) -> bool:
    digits = "".join(ch for ch in (card_number or "") if ch.isdigit())
    if len(digits) != 16 or not digits.startswith("8866"):
        return False
    expected = compute_luhn_check_digit(digits[:15])
    return digits[15] == expected


def mint_prepaid_card_batch_preview(sku_code: str, start_serial: int, count: int) -> List[LegacyPrepaidCardRecord]:
    spec = CARD_DENOMINATIONS_CENTS.get(sku_code, CARD_DENOMINATIONS_CENTS["YC24_GIFT_200"])
    batch: List[LegacyPrepaidCardRecord] = []
    safe_cnt = max(0, min(500, int(count)))

    for offset in range(safe_cnt):
        seq = int(start_serial) + offset
        stem = f"88662024{seq:07d}"[:15]
        chk = compute_luhn_check_digit(stem)
        batch.append(
            LegacyPrepaidCardRecord(
                card_number=stem + chk,
                sku_code=sku_code,
                face_cents=int(spec["face_cents"]),
                target_bucket=str(spec["bucket"]),
                status="ISSUED",
            )
        )
    return batch


def simulate_legacy_card_redemption(card: LegacyPrepaidCardRecord, tenant_id: str) -> Dict[str, Any]:
    if not verify_prepaid_card_number(card.card_number):
        return {"accepted": False, "error": "INVALID_CARD_LUHN_CHECKSUM"}
    if card.status != "ISSUED":
        return {"accepted": False, "error": f"CARD_NOT_REDEEMABLE:{card.status}"}

    card.status = "REDEEMED"
    card.redeemed_by_tenant = tenant_id
    return {
        "accepted": True,
        "card_number": card.card_number,
        "tenant_id": tenant_id,
        "credited_bucket": card.target_bucket,
        "credited_cents": card.face_cents,
    }
