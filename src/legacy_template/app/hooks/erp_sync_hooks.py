# -*- coding: utf-8 -*-
"""财务总账与外部金蝶/SAP 凭证同步水位内存跟踪钩子。"""
import threading
from typing import Dict, List

from app.infra.events import event_bus
from app.infra.metrics_collector import runtime_metrics

_erp_lock = threading.Lock()
_pending_voucher_refs: List[Dict[str, object]] = []


def on_invoice_paid_for_erp(payload: dict) -> None:
    runtime_metrics.inc("erp.voucher_queued.paid")
    with _erp_lock:
        if len(_pending_voucher_refs) >= 256:
            del _pending_voucher_refs[:128]
        _pending_voucher_refs.append({
            "kind": "CASH_RECEIPT",
            "invoice_id": payload.get("invoice_id"),
            "tenant_id": payload.get("tenant_id"),
            "amount_cents": payload.get("amount_cents", 0),
        })


def on_invoice_refunded_for_erp(payload: dict) -> None:
    runtime_metrics.inc("erp.voucher_queued.refunded")
    with _erp_lock:
        if len(_pending_voucher_refs) >= 256:
            del _pending_voucher_refs[:128]
        _pending_voucher_refs.append({
            "kind": "REFUND_REVERSAL",
            "invoice_id": payload.get("invoice_id"),
            "tenant_id": payload.get("tenant_id"),
            "refund_cents": payload.get("refund_cents", 0),
        })


def get_pending_erp_voucher_queue() -> List[Dict[str, object]]:
    with _erp_lock:
        return list(_pending_voucher_refs)


def register_erp_sync_hooks() -> None:
    event_bus.subscribe("invoice.paid", on_invoice_paid_for_erp)
    event_bus.subscribe("invoice.refunded", on_invoice_refunded_for_erp)
