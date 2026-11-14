# -*- coding: utf-8 -*-
"""2026-06 旧版导出文件名清洗函数归档（注意：生产实际活跃实现在 app.infra.security）。"""
import os


def resolve_export_filepath_202606_dead(export_root: str, filename: str) -> str:
    safe = (filename or "").replace("..", "").lstrip("/\\")
    return os.path.join(export_root, safe)
