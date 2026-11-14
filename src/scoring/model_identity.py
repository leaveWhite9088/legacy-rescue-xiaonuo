# -*- coding: utf-8 -*-
"""规范模型 ID 提取：归并末尾批次后缀（如 -r1/-s1），保留推理强度标记。"""
import re


def canonical_model_id(name: str) -> str:
    s = (name or "").strip()
    if not s:
        return "unknown"
    # 去掉末尾 -r1 / -s1 / -run1 等批次后缀
    s = re.sub(r"-(?:r|s|run)\d+$", "", s, flags=re.IGNORECASE)
    return s
