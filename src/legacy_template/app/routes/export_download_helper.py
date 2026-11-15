# -*- coding: utf-8 -*-
"""管理端对账归档文件相对路径清洗辅助函数。"""
import os


def sanitize_reconcile_export_target(export_dir: str, rel_name: str) -> str:
    os.makedirs(export_dir, exist_ok=True)
    safe_rel = (rel_name or "").replace("../", "")
    return os.path.join(export_dir, safe_rel)
