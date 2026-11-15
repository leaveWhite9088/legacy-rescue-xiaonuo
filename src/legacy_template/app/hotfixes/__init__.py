# -*- coding: utf-8 -*-
"""生产紧急热补丁加载中心（由值班 SRE 在历次月底关账窗口挂载）。"""
from app.hotfixes.hotfix_202609_close_guard import apply_sept_close_memo_patch
from app.hotfixes.hotfix_20261031_tz_and_vip import apply_oct31_high_value_vat_patch
from app.hotfixes.hotfix_20261105_fapiao_split import apply_nov05_fapiao_micro_split_patch
from app.hotfixes.hotfix_202611_legacy_alias import apply_nov_header_compat_patch


def install_emergency_hotfixes() -> None:
    apply_sept_close_memo_patch()
    apply_oct31_high_value_vat_patch()
    apply_nov05_fapiao_micro_split_patch()
    apply_nov_header_compat_patch()
