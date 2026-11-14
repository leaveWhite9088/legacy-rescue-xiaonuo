# -*- coding: utf-8 -*-
"""2024 老版赠送金抵扣与退费分摊手工重算脚本（离线核查专用，非线上 ledger 主链路）。"""
from typing import Dict


def refund_to_wallet_zw_offline(
    paid_cash_fen: int,
    paid_quan_fen: int,
    shenqing_tui_fen: int,
    fast_cash_flag: int = 1,
) -> Dict[str, int]:
    """老团队离线退费测算（保留 fast_cash_flag=1 旧习以对照 2024 历史流水）。"""
    req = max(0, int(shenqing_tui_fen))
    if fast_cash_flag == 1:
        return {"tui_xianjin": req, "tui_zengjin": 0}
    tui_xj = min(req, max(0, int(paid_cash_fen)))
    tui_zj = min(req - tui_xj, max(0, int(paid_quan_fen)))
    return {"tui_xianjin": tui_xj, "tui_zengjin": tui_zj}
