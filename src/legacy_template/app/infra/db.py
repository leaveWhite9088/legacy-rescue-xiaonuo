# -*- coding: utf-8 -*-
"""SQLite 持久化层、事务上下文、多子系统表结构定义与 2024 v1 异构老租户兼容适配层。"""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
import sqlite3
from typing import Any, Dict, Optional
import uuid

from app.infra.config import DB_PATH
from app.legacy_v1.v1_currency_shim import parse_v1_yuan_string


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_id(prefix: str = "rec") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    path = db_path or os.environ.get("YUNCE_DB_PATH") or DB_PATH
    conn = sqlite3.connect(path, timeout=10.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


@contextmanager
def tx_context(db_path: Optional[str] = None, immediate: bool = False):
    conn = get_connection(db_path)
    try:
        if immediate:
            conn.execute("BEGIN IMMEDIATE;")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS tenants (
            id TEXT PRIMARY KEY,
            company_name TEXT NOT NULL,
            api_token TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'ACTIVE',
            tier_level TEXT NOT NULL DEFAULT 'STANDARD',
            tax_profile_code TEXT NOT NULL DEFAULT 'CN_VAT_6_INCLUSIVE',
            partner_code TEXT DEFAULT NULL,
            webhook_url TEXT DEFAULT '',
            schema_version INTEGER NOT NULL DEFAULT 2,
            billing_metadata TEXT DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS enterprise_contracts (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL UNIQUE,
            min_monthly_commit_cents INTEGER NOT NULL DEFAULT 0,
            custom_overage_discount_bps INTEGER NOT NULL DEFAULT 0,
            credit_memo_bps INTEGER NOT NULL DEFAULT 0,
            credit_limit_cents INTEGER NOT NULL DEFAULT 0,
            signed_by TEXT NOT NULL DEFAULT 'sales_ops',
            valid_from TEXT NOT NULL,
            valid_until TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'ACTIVE',
            FOREIGN KEY (tenant_id) REFERENCES tenants(id)
        );

        CREATE TABLE IF NOT EXISTS subscriptions (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            plan_code TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'ACTIVE',
            cycle_start TEXT NOT NULL,
            cycle_end TEXT NOT NULL,
            next_billing_at TEXT NOT NULL,
            auto_renew INTEGER NOT NULL DEFAULT 1,
            tier_mode TEXT DEFAULT 'PROGRESSIVE',
            legacy_contract_override TEXT DEFAULT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (tenant_id) REFERENCES tenants(id)
        );

        CREATE TABLE IF NOT EXISTS plan_change_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subscription_id TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            old_plan_code TEXT NOT NULL,
            new_plan_code TEXT NOT NULL,
            effective_at TEXT NOT NULL,
            proration_cents INTEGER NOT NULL DEFAULT 0,
            reason TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS wallets (
            tenant_id TEXT PRIMARY KEY,
            cash_balance_cents INTEGER NOT NULL DEFAULT 0,
            promo_balance_cents INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (tenant_id) REFERENCES tenants(id)
        );

        CREATE TABLE IF NOT EXISTS promo_grants (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            initial_cents INTEGER NOT NULL,
            remaining_cents INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'ACTIVE',
            expires_at TEXT NOT NULL,
            campaign_code TEXT DEFAULT 'OPS_GRANT',
            created_at TEXT NOT NULL,
            FOREIGN KEY (tenant_id) REFERENCES tenants(id)
        );

        CREATE TABLE IF NOT EXISTS wallet_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id TEXT NOT NULL,
            entry_type TEXT NOT NULL,
            cash_delta_cents INTEGER NOT NULL DEFAULT 0,
            promo_delta_cents INTEGER NOT NULL DEFAULT 0,
            ref_id TEXT DEFAULT '',
            note TEXT DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS usage_events (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            metric_code TEXT NOT NULL DEFAULT 'API_CALLS',
            quantity INTEGER NOT NULL,
            plan_code_at_event TEXT DEFAULT NULL,
            occurred_at TEXT NOT NULL,
            period_key TEXT NOT NULL,
            flushed INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS usage_summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id TEXT NOT NULL,
            period_key TEXT NOT NULL,
            plan_code TEXT NOT NULL,
            total_quantity INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            UNIQUE(tenant_id, period_key, plan_code)
        );

        CREATE TABLE IF NOT EXISTS accounting_periods (
            period_key TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'OPEN',
            closed_at TEXT DEFAULT NULL,
            closed_by TEXT DEFAULT NULL,
            archived_total_cents INTEGER DEFAULT NULL
        );

        CREATE TABLE IF NOT EXISTS invoices (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            period_key TEXT NOT NULL,
            cycle_start TEXT NOT NULL,
            cycle_end TEXT NOT NULL,
            plan_code TEXT NOT NULL,
            base_fee_cents INTEGER NOT NULL DEFAULT 0,
            overage_fee_cents INTEGER NOT NULL DEFAULT 0,
            tax_cents INTEGER NOT NULL DEFAULT 0,
            late_fee_cents INTEGER NOT NULL DEFAULT 0,
            total_cents INTEGER NOT NULL DEFAULT 0,
            paid_cents INTEGER NOT NULL DEFAULT 0,
            refunded_cents INTEGER NOT NULL DEFAULT 0,
            currency_unit TEXT NOT NULL DEFAULT 'CENTS',
            raw_legacy_total TEXT DEFAULT NULL,
            status TEXT NOT NULL DEFAULT 'OPEN',
            dispute_reason TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (tenant_id) REFERENCES tenants(id)
        );

        CREATE TABLE IF NOT EXISTS invoice_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id TEXT NOT NULL,
            line_type TEXT NOT NULL,
            description TEXT NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 0,
            unit_price_cents INTEGER NOT NULL DEFAULT 0,
            amount_cents INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (invoice_id) REFERENCES invoices(id)
        );

        CREATE TABLE IF NOT EXISTS invoice_payments (
            id TEXT PRIMARY KEY,
            invoice_id TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            idempotency_key TEXT DEFAULT NULL,
            cash_paid_cents INTEGER NOT NULL DEFAULT 0,
            promo_paid_cents INTEGER NOT NULL DEFAULT 0,
            total_paid_cents INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (invoice_id) REFERENCES invoices(id)
        );

        CREATE TABLE IF NOT EXISTS billing_adjustments (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            ref_invoice_id TEXT NOT NULL,
            target_period_key TEXT NOT NULL,
            applied_period_key TEXT NOT NULL,
            adjustment_type TEXT NOT NULL,
            delta_cents INTEGER NOT NULL,
            reason TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS partner_referrals (
            partner_code TEXT NOT NULL,
            tenant_id TEXT NOT NULL UNIQUE,
            partner_tier TEXT NOT NULL DEFAULT 'SILVER',
            bound_at TEXT NOT NULL,
            PRIMARY KEY (partner_code, tenant_id)
        );

        CREATE TABLE IF NOT EXISTS partner_commissions (
            id TEXT PRIMARY KEY,
            partner_code TEXT NOT NULL,
            period_key TEXT NOT NULL,
            net_cash_collected_cents INTEGER NOT NULL DEFAULT 0,
            commission_cents INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'CALCULATED',
            created_at TEXT NOT NULL,
            UNIQUE(partner_code, period_key)
        );

        CREATE TABLE IF NOT EXISTS gl_journal_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            period_key TEXT NOT NULL,
            ref_type TEXT NOT NULL,
            ref_id TEXT NOT NULL,
            debit_account TEXT NOT NULL,
            credit_account TEXT NOT NULL,
            amount_cents INTEGER NOT NULL,
            debit_cents INTEGER NOT NULL DEFAULT 0,
            credit_cents INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS webhook_outbox (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            signature TEXT NOT NULL,
            delivery_status TEXT NOT NULL DEFAULT 'QUEUED',
            attempts INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS settlement_dlq (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            error_msg TEXT NOT NULL,
            retry_count INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'PENDING',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS fapiao_requests (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            invoice_id TEXT NOT NULL,
            fapiao_type TEXT NOT NULL DEFAULT 'VAT_SPECIAL_E',
            buyer_tax_id TEXT NOT NULL,
            title TEXT NOT NULL,
            net_amount_cents INTEGER NOT NULL DEFAULT 0,
            tax_amount_cents INTEGER NOT NULL DEFAULT 0,
            gross_amount_cents INTEGER NOT NULL DEFAULT 0,
            sheet_count INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'ISSUED',
            red_letter_of TEXT DEFAULT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (tenant_id) REFERENCES tenants(id),
            FOREIGN KEY (invoice_id) REFERENCES invoices(id)
        );

        CREATE TABLE IF NOT EXISTS dunning_cases (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            invoice_id TEXT NOT NULL,
            stage TEXT NOT NULL DEFAULT 'GRACE',
            overdue_days INTEGER NOT NULL DEFAULT 0,
            unpaid_cents INTEGER NOT NULL DEFAULT 0,
            last_notified_at TEXT DEFAULT NULL,
            status TEXT NOT NULL DEFAULT 'OPEN',
            updated_at TEXT NOT NULL,
            FOREIGN KEY (tenant_id) REFERENCES tenants(id),
            FOREIGN KEY (invoice_id) REFERENCES invoices(id)
        );

        CREATE TABLE IF NOT EXISTS bank_statement_imports (
            id TEXT PRIMARY KEY,
            bank_serial_no TEXT NOT NULL UNIQUE,
            payer_company_name TEXT NOT NULL,
            amount_cents INTEGER NOT NULL,
            tx_date TEXT NOT NULL,
            matched_tenant_id TEXT DEFAULT NULL,
            match_confidence_bps INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'UNMATCHED',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS approval_tickets (
            id TEXT PRIMARY KEY,
            ticket_type TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            ref_object_id TEXT NOT NULL,
            amount_cents INTEGER NOT NULL DEFAULT 0,
            requested_by TEXT NOT NULL,
            first_approver TEXT DEFAULT NULL,
            second_approver TEXT DEFAULT NULL,
            required_approvals INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'PENDING',
            reason TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sla_credit_claims (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            period_key TEXT NOT NULL,
            observed_uptime_bps INTEGER NOT NULL,
            promised_uptime_bps INTEGER NOT NULL,
            credit_cents INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'EVALUATED',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sys_runtime_configs (
            config_key TEXT PRIMARY KEY,
            config_value TEXT NOT NULL,
            env_scope TEXT NOT NULL DEFAULT 'PROD',
            updated_by TEXT NOT NULL DEFAULT 'system',
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS dispute_tickets (
            id TEXT PRIMARY KEY,
            invoice_id TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            reason TEXT NOT NULL,
            freeze_auto_debit INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'OPEN',
            created_at TEXT NOT NULL,
            resolved_at TEXT DEFAULT NULL,
            FOREIGN KEY (invoice_id) REFERENCES invoices(id)
        );

        CREATE TABLE IF NOT EXISTS credit_notes (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            source_invoice_id TEXT NOT NULL,
            credit_cents INTEGER NOT NULL,
            remaining_cents INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'ISSUED',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS idempotency_records (
            idem_key TEXT PRIMARY KEY,
            scope TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            response_json TEXT NOT NULL,
            status_code INTEGER NOT NULL DEFAULT 200,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            target_id TEXT NOT NULL,
            detail TEXT DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS fx_rates (
            currency_code TEXT NOT NULL,
            effective_date TEXT NOT NULL,
            rate_bps INTEGER NOT NULL,
            source TEXT NOT NULL DEFAULT 'PBOC_MID',
            PRIMARY KEY (currency_code, effective_date)
        );

        CREATE TABLE IF NOT EXISTS fx_settlement_logs (
            id TEXT PRIMARY KEY,
            invoice_id TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            currency_code TEXT NOT NULL,
            foreign_minor_units INTEGER NOT NULL,
            applied_rate_bps INTEGER NOT NULL,
            settled_cny_cents INTEGER NOT NULL,
            unrealized_gain_loss_cents INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS escrow_accounts (
            tenant_id TEXT PRIMARY KEY,
            initial_deposit_cents INTEGER NOT NULL DEFAULT 0,
            balance_cents INTEGER NOT NULL DEFAULT 0,
            frozen_cents INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'ACTIVE',
            updated_at TEXT NOT NULL,
            FOREIGN KEY (tenant_id) REFERENCES tenants(id)
        );

        CREATE TABLE IF NOT EXISTS deferred_revenue_schedules (
            id TEXT PRIMARY KEY,
            invoice_id TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            period_key TEXT NOT NULL,
            recognized_cents INTEGER NOT NULL DEFAULT 0,
            deferred_closing_cents INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'DEFERRED',
            updated_at TEXT NOT NULL,
            UNIQUE(invoice_id, period_key)
        );

        CREATE TABLE IF NOT EXISTS partner_hierarchy (
            child_partner_code TEXT PRIMARY KEY,
            parent_partner_code TEXT NOT NULL,
            parent_tier_bps INTEGER NOT NULL,
            child_tier_bps INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'ACTIVE'
        );
        """
    )


# ---------------------------------------------------------------------------
# 2024 Q4 早期大客户迁移兼容层（委托 legacy_v1 货币解析工具）
# ugly v1 hack, maybe clean up someday when all v1 contracts expire
# ---------------------------------------------------------------------------
def parse_legacy_amount_cents(row_dict: Dict[str, Any], field: str = "total_cents") -> int:
    """兼容早期 v1 迁移账单用字符串元 (YUAN_STR) 存储金额的历史遗留记录。"""
    if row_dict.get("currency_unit") == "YUAN_STR" and row_dict.get("raw_legacy_total"):
        return parse_v1_yuan_string(row_dict["raw_legacy_total"], fallback_cents=int(row_dict.get(field) or 0))
    val = row_dict.get(field, 0)
    if isinstance(val, str):
        return parse_v1_yuan_string(val, fallback_cents=0)
    return int(val or 0)


def normalize_tenant_record(row: sqlite3.Row) -> Dict[str, Any]:
    """把 v1 异构租户记录统一补齐为系统可识别的字典视图。"""
    d = dict(row)
    meta = {}
    if d.get("billing_metadata"):
        try:
            meta = json.loads(d["billing_metadata"])
        except Exception:
            meta = {}
    d["meta"] = meta
    if d.get("schema_version") == 1 or d.get("status") == "ACTIVE_LEGACY":
        d["is_legacy_v1"] = True
        d["effective_status"] = "ACTIVE"
        d["legacy_discount_bps"] = int(meta.get("legacy_discount_bps", 0))
        d["tax_profile_code"] = d.get("tax_profile_code") or "EXEMPT"
    else:
        d["is_legacy_v1"] = False
        d["effective_status"] = d.get("status", "ACTIVE")
        d["legacy_discount_bps"] = 0
        d["tax_profile_code"] = d.get("tax_profile_code") or "CN_VAT_6_INCLUSIVE"
    return d
