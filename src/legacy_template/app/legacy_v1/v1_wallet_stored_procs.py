# -*- coding: utf-8 -*-
"""2024 钱包存储过程模拟器与冻结担保金管理遗留模块（非线上活跃账本引擎）。
线上实时账本位于 app.domain.ledger 及 app.compat.wallet_bridge。
"""
from datetime import datetime, timezone
import sqlite3
from typing import Any, Dict, List, Optional


class V1WalletEscrowSimulator:
    """2024 大客户线下授信保证金与赠送金批次台账模拟器。"""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    @staticmethod
    def _ts() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def compute_ledger_trial_balance_v1(self, tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """对比 wallets 快照余额与 wallet_ledger 历史流水累加值（离线核账工具）。"""
        if tenant_id:
            wallets = self.conn.execute("SELECT * FROM wallets WHERE tenant_id = ?", (tenant_id,)).fetchall()
        else:
            wallets = self.conn.execute("SELECT * FROM wallets ORDER BY tenant_id").fetchall()

        report: List[Dict[str, Any]] = []
        for w in wallets:
            tid = w["tenant_id"]
            sums = self.conn.execute(
                """
                SELECT COALESCE(SUM(cash_delta_cents), 0) AS sum_cash,
                       COALESCE(SUM(promo_delta_cents), 0) AS sum_promo,
                       COUNT(*) AS entry_cnt
                FROM wallet_ledger
                WHERE tenant_id = ?
                """,
                (tid,),
            ).fetchone()
            snap_c = int(w["cash_balance_cents"])
            snap_p = int(w["promo_balance_cents"])
            led_c = int(sums["sum_cash"])
            led_p = int(sums["sum_promo"])
            report.append({
                "tenant_id": tid,
                "snapshot_cash_cents": snap_c,
                "ledger_cash_cents": led_c,
                "cash_drift_cents": snap_c - led_c,
                "snapshot_promo_cents": snap_p,
                "ledger_promo_cents": led_p,
                "promo_drift_cents": snap_p - led_p,
                "entry_count": int(sums["entry_cnt"]),
                "is_consistent": (snap_c == led_c and snap_p == led_p and snap_c >= 0 and snap_p >= 0),
            })
        return report

    def simulate_fifo_grant_consumption(self, tenant_id: str, target_spend_cents: int) -> Dict[str, Any]:
        """模拟按到期时间先后顺序（FEFO）核销赠送金券。"""
        grants = self.conn.execute(
            """
            SELECT id, initial_cents, remaining_cents, expires_at, campaign_code
            FROM promo_grants
            WHERE tenant_id = ? AND status = 'ACTIVE' AND remaining_cents > 0
            ORDER BY expires_at ASC, id ASC
            """,
            (tenant_id,),
        ).fetchall()

        rem = max(0, int(target_spend_cents))
        allocations = []
        for g in grants:
            if rem <= 0:
                break
            take = min(rem, int(g["remaining_cents"]))
            allocations.append({
                "grant_id": g["id"],
                "campaign_code": g["campaign_code"],
                "expires_at": g["expires_at"],
                "deduct_cents": take,
                "after_remaining_cents": int(g["remaining_cents"]) - take,
            })
            rem -= take

        return {
            "tenant_id": tenant_id,
            "requested_promo_cents": int(target_spend_cents),
            "covered_promo_cents": int(target_spend_cents) - rem,
            "shortfall_cash_needed_cents": rem,
            "allocations": allocations,
        }

    def preview_expired_grants_cleanup_v1(self, cutoff_iso: str) -> List[Dict[str, Any]]:
        """预览截至指定时间尚未过期处理但已过有效期的券（只读预览，不执行写库）。"""
        rows = self.conn.execute(
            """
            SELECT id, tenant_id, initial_cents, remaining_cents, status, expires_at
            FROM promo_grants
            WHERE expires_at <= ? AND status = 'ACTIVE'
            ORDER BY expires_at ASC
            """,
            (cutoff_iso,),
        ).fetchall()
        return [
            {
                "grant_id": r["id"],
                "tenant_id": r["tenant_id"],
                "initial_cents": int(r["initial_cents"]),
                "remaining_to_expire_cents": int(r["remaining_cents"]),
                "expires_at": r["expires_at"],
            }
            for r in rows
        ]

    def rebuild_legacy_voucher_digest(self, tenant_id: str) -> str:
        rows = self.conn.execute(
            "SELECT entry_type, cash_delta_cents, promo_delta_cents, ref_id FROM wallet_ledger WHERE tenant_id = ? ORDER BY id ASC",
            (tenant_id,),
        ).fetchall()
        parts = [f"{r['entry_type']}:{r['cash_delta_cents']}:{r['promo_delta_cents']}:{r['ref_id']}" for r in rows]
        return "|".join(parts)
