# -*- coding: utf-8 -*-
"""跨境与多地域租户账单归档数据驻留（Data Residency: PIPL / PDPA / GDPR）存储桶路由策略。"""
from typing import Dict


RESIDENCY_POLICIES: Dict[str, Dict[str, str]] = {
    "CN_MAINLAND": {
        "regulation": "CN_PIPL_AND_CSL",
        "primary_archive_bucket": "oss-cn-shanghai-finance-worm",
        "dr_archive_bucket": "oss-cn-beijing-finance-worm",
        "cross_border_export_allowed": "FALSE",
    },
    "SINGAPORE_APAC": {
        "regulation": "SG_PDPA_2024",
        "primary_archive_bucket": "s3-ap-southeast-1-billing-archive",
        "dr_archive_bucket": "s3-ap-northeast-1-billing-archive",
        "cross_border_export_allowed": "WITH_DPA_ADDENDUM",
    },
}


def resolve_archive_residency_for_tax_profile(tax_profile_code: str) -> Dict[str, str]:
    if tax_profile_code == "SG_GST_9_EXCLUSIVE":
        return dict(RESIDENCY_POLICIES["SINGAPORE_APAC"])
    return dict(RESIDENCY_POLICIES["CN_MAINLAND"])
