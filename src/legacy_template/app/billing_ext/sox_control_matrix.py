# -*- coding: utf-8 -*-
"""SOX 404 萨班斯财务内控自动化控制点评估矩阵（C01 ~ C06 只读合规检查）。"""
import sqlite3
from typing import Any, Dict, List

from app.domain.gl_exporter import generate_gl_entries_for_period
from app.domain.subledger_reconciler import audit_closed_period_seals
from app.reporting.audit_trail_forensics import scan_billing_forensic_anomalies


def run_sox_control_assessment(conn: sqlite3.Connection, open_period: str = "2026-11") -> Dict[str, Any]:
    seals = audit_closed_period_seals(conn)
    forensics = scan_billing_forensic_anomalies(conn, open_period)
    gl_summary = generate_gl_entries_for_period(conn, open_period)
    gl_balanced = bool(gl_summary.get("balanced", True))

    # 核验已终审工单的提单人与终审签批人职责分离关系
    sod_rows = conn.execute(
        """
        SELECT id FROM approval_tickets
        WHERE status = 'APPROVED'
          AND second_approver IS NOT NULL
          AND requested_by = second_approver
        """
    ).fetchall()
    sod_violations = len(sod_rows)

    controls: List[Dict[str, Any]] = [
        {
            "control_id": "SOX-FIN-01",
            "name": "已封账会计期间总额不可篡改性",
            "effective": all(s["seal_intact"] for s in seals),
            "evidence_count": len(seals),
        },
        {
            "control_id": "SOX-FIN-02",
            "name": "总账凭证借贷方发生额试算平衡控制",
            "effective": gl_balanced,
            "exceptions": 0 if gl_balanced else 1,
        },
        {
            "control_id": "SOX-FIN-03",
            "name": "金税发票开具金额不超原账单总额控制",
            "effective": len(forensics["fapiao_over_issuance"]) == 0,
            "exceptions": len(forensics["fapiao_over_issuance"]),
        },
        {
            "control_id": "SOX-FIN-04",
            "name": "收款核销子表与主账单外键完备性控制",
            "effective": len(forensics["orphan_invoice_payments"]) == 0,
            "exceptions": len(forensics["orphan_invoice_payments"]),
        },
        {
            "control_id": "SOX-FIN-05",
            "name": "银企直联水单当期未达账项清零控制",
            "effective": len(forensics["unmatched_bank_statements"]) == 0,
            "exceptions": len(forensics["unmatched_bank_statements"]),
        },
        {
            "control_id": "SOX-FIN-06",
            "name": "大额调账双签积压与职责分离（SoD）控制",
            "effective": len(forensics["high_value_pending_approvals"]) == 0 and sod_violations == 0,
            "exceptions": len(forensics["high_value_pending_approvals"]) + sod_violations,
            "sod_violations": sod_violations,
        },
    ]

    passed_cnt = sum(1 for c in controls if c["effective"])
    return {
        "open_period_evaluated": open_period,
        "total_controls": len(controls),
        "effective_controls": passed_cnt,
        "deficient_controls": len(controls) - passed_cnt,
        "controls": controls,
    }
