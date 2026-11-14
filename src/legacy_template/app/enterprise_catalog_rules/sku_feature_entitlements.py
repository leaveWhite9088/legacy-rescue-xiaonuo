# -*- coding: utf-8 -*-
"""各订阅套餐 SKU 功能模块授权开关（RBAC / SSO / 审计保留天数 / 并发沙盒槽位数）定义表。"""
from typing import Any, Dict


SKU_ENTITLEMENTS: Dict[str, Dict[str, Any]] = {
    "LEGACY_FLAT_99": {
        "sso_saml_enabled": False,
        "audit_log_retention_days": 30,
        "max_concurrent_sandboxes": 2,
        "dedicated_support_csm": False,
        "custom_tax_invoice": True,
    },
    "STARTER": {
        "sso_saml_enabled": False,
        "audit_log_retention_days": 30,
        "max_concurrent_sandboxes": 4,
        "dedicated_support_csm": False,
        "custom_tax_invoice": True,
    },
    "PRO": {
        "sso_saml_enabled": True,
        "audit_log_retention_days": 180,
        "max_concurrent_sandboxes": 16,
        "dedicated_support_csm": False,
        "custom_tax_invoice": True,
    },
    "ENTERPRISE": {
        "sso_saml_enabled": True,
        "audit_log_retention_days": 730,
        "max_concurrent_sandboxes": 128,
        "dedicated_support_csm": True,
        "custom_tax_invoice": True,
    },
}


def get_plan_entitlement_matrix(plan_code: str) -> Dict[str, Any]:
    return dict(SKU_ENTITLEMENTS.get(plan_code, SKU_ENTITLEMENTS["STARTER"]))
