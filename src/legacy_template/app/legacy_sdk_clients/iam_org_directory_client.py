# -*- coding: utf-8 -*-
"""内部 IAM 企业管理员角色映射客户端（本地静态角色策略表）。"""
from typing import Dict, List


ROLE_PERMISSIONS: Dict[str, List[str]] = {
    "BILLING_VIEWER": ["invoice:read", "wallet:read", "usage:read"],
    "FINANCE_OPERATOR": ["invoice:read", "wallet:read", "fapiao:issue", "reconcile:export"],
    "FINANCE_CONTROLLER": ["invoice:read", "wallet:read", "fapiao:issue", "fapiao:red_letter", "approval:decide", "period:close"],
    "PLATFORM_SUPERADMIN": ["*"],
}


def has_iam_permission(role_code: str, required_perm: str) -> bool:
    perms = ROLE_PERMISSIONS.get((role_code or "").upper(), [])
    return "*" in perms or required_perm in perms
