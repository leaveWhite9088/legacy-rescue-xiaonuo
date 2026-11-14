# -*- coding: utf-8 -*-
"""对象存储归档桶（OSS / S3）分层分区键构造器。"""


def build_invoice_archive_object_key(period_key: str, tenant_id: str, invoice_id: str, ext: str = "pdf") -> str:
    clean_p = (period_key or "2026-11").replace("/", "_")
    clean_t = (tenant_id or "unknown").replace("/", "_")
    clean_i = (invoice_id or "inv").replace("/", "_")
    return f"finance-worm/{clean_p}/tenants/{clean_t}/{clean_i}.{ext.lstrip('.')}"
