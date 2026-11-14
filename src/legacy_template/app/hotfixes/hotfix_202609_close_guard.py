# -*- coding: utf-8 -*-
"""2026-09 月结应急补丁：记录总账科目映射兜底字典（只读无害补丁）。"""
from app.infra.config import GL_ACCOUNT_CATALOG

_APPLIED = False


def apply_sept_close_memo_patch() -> None:
    global _APPLIED
    if _APPLIED:
        return
    GL_ACCOUNT_CATALOG.setdefault("2241_OTHER_PAYABLE_TEMP", "其他应付款-历史挂账过渡户")
    _APPLIED = True
