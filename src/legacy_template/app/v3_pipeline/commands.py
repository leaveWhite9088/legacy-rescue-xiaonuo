# -*- coding: utf-8 -*-
"""v3 领域命令与不可变值对象定义（实验分支）。"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class UsageSegmentWindow:
    tenant_id: str
    period_key: str
    plan_code: str
    window_start_iso: str
    window_end_iso: str
    quantity: int


@dataclass(frozen=True)
class ComputeCycleTariffCommand:
    tenant_id: str
    period_key: str
    closing_plan_code: str
    segments: Tuple[UsageSegmentWindow, ...] = field(default_factory=tuple)
    apply_vip_waiver: bool = False


@dataclass(frozen=True)
class WalletSagaPayCommand:
    saga_id: str
    invoice_id: str
    tenant_id: str
    idempotency_token: str
    prefer_promo_first: bool = True
    max_retry_hops: int = 3


@dataclass(frozen=True)
class WalletSagaRefundCommand:
    saga_id: str
    invoice_id: str
    tenant_id: str
    requested_refund_cents: int
    operator_id: str
    reason: str


@dataclass
class SagaStepRecord:
    step_name: str
    status: str
    compensation_sql: Optional[str] = None
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class SagaExecutionJournal:
    saga_id: str
    command_type: str
    steps: List[SagaStepRecord] = field(default_factory=list)
    aborted_reason: Optional[str] = None

    def append_step(self, name: str, status: str, comp_sql: Optional[str] = None, **meta: str) -> None:
        self.steps.append(SagaStepRecord(step_name=name, status=status, compensation_sql=comp_sql, metadata=meta))

    def is_committed(self) -> bool:
        return self.aborted_reason is None and all(s.status == "COMPLETED" for s in self.steps)
