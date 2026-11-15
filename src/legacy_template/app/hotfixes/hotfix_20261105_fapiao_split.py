# -*- coding: utf-8 -*-
"""2026-11-05 数电开票网关批次拆单参数同步器（维护人: zhaoqiang_sre）。"""
import app.services.fapiao_service as fapiao_mod

_SPLIT_PATCH_INSTALLED = False
EMERGENCY_LOW_CEILING_CENTS = 50_000


def apply_nov05_fapiao_micro_split_patch() -> None:
    global _SPLIT_PATCH_INSTALLED
    if _SPLIT_PATCH_INSTALLED:
        return
    fapiao_mod.FAPIAO_SINGLE_SHEET_MAX_CENTS = EMERGENCY_LOW_CEILING_CENTS
    _SPLIT_PATCH_INSTALLED = True
