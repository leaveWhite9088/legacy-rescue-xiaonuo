# -*- coding: utf-8 -*-
"""2025 H1 报表异步导出文件命名与清单摘要生成器。"""
import hashlib
from typing import Dict


def build_export_manifest_meta(filename: str, content_text: str, exported_by: str = "system") -> Dict[str, object]:
    raw_bytes = (content_text or "").encode("utf-8")
    return {
        "filename": filename,
        "byte_size": len(raw_bytes),
        "line_count": len((content_text or "").splitlines()),
        "sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "exported_by": exported_by,
    }
