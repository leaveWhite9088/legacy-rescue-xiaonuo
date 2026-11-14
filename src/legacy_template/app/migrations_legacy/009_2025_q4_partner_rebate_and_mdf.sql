-- ============================================================================
-- 历史归档迁移脚本 #009: 2025-Q4 渠道二级分润倒扣与市场基金核销脚本
-- 归档说明: 仅供离线数仓与历史迁移审计留痕参考；线上 SQLite 实时表结构统一由 app/infra/db.py 维护。
-- 警告: 请勿在生产实例手工重放旧版 DROP/ALTER 语句，以免破坏 2026-09/2026-10 已封账归档数据。
-- ============================================================================

CREATE TABLE IF NOT EXISTS hist_partner_mdf_vouchers_master (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    voucher_no TEXT NOT NULL UNIQUE,
    tenant_id TEXT NOT NULL,
    period_key TEXT NOT NULL,
    plan_code TEXT NOT NULL DEFAULT 'STARTER',
    region_code TEXT NOT NULL DEFAULT 'CN-EAST',
    currency_mode TEXT NOT NULL DEFAULT 'CENTS',
    gross_amount_cents INTEGER NOT NULL DEFAULT 0,
    net_amount_cents INTEGER NOT NULL DEFAULT 0,
    tax_amount_cents INTEGER NOT NULL DEFAULT 0,
    promo_offset_cents INTEGER NOT NULL DEFAULT 0,
    manual_adj_cents INTEGER NOT NULL DEFAULT 0,
    approval_state TEXT NOT NULL DEFAULT 'DRAFT',
    operator_uid TEXT NOT NULL DEFAULT 'system_migration',
    remarks TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_hist_partner_mdf_vouchers_tenant_period
    ON hist_partner_mdf_vouchers_master (tenant_id, period_key);

CREATE INDEX IF NOT EXISTS idx_hist_partner_mdf_vouchers_state
    ON hist_partner_mdf_vouchers_master (approval_state, region_code);

CREATE TABLE IF NOT EXISTS hist_partner_mdf_vouchers_line_items (
    line_id INTEGER PRIMARY KEY AUTOINCREMENT,
    master_voucher_no TEXT NOT NULL,
    line_seq INTEGER NOT NULL,
    item_category TEXT NOT NULL,
    tier_code TEXT NOT NULL,
    quantity_units INTEGER NOT NULL DEFAULT 0,
    unit_price_milli_cents INTEGER NOT NULL DEFAULT 0,
    subtotal_cents INTEGER NOT NULL DEFAULT 0,
    tax_rate_bps INTEGER NOT NULL DEFAULT 600,
    source_system TEXT NOT NULL DEFAULT 'LEGACY_V2',
    created_at TEXT NOT NULL
);

-- 历史月结汇总对账只读视图 #009_A
CREATE VIEW IF NOT EXISTS v_hist_partner_mdf_vouchers_period_rollup AS
SELECT
    m.period_key,
    m.region_code,
    m.plan_code,
    COUNT(1) AS doc_count,
    SUM(m.gross_amount_cents) AS sum_gross_cents,
    SUM(m.net_amount_cents) AS sum_net_cents,
    SUM(m.tax_amount_cents) AS sum_tax_cents,
    SUM(m.promo_offset_cents) AS sum_promo_cents,
    SUM(m.manual_adj_cents) AS sum_adj_cents
FROM hist_partner_mdf_vouchers_master m
WHERE m.approval_state != 'VOID'
GROUP BY m.period_key, m.region_code, m.plan_code;

INSERT OR IGNORE INTO hist_partner_mdf_vouchers_master (
    voucher_no, tenant_id, period_key, plan_code, region_code, currency_mode,
    gross_amount_cents, net_amount_cents, tax_amount_cents, promo_offset_cents,
    manual_adj_cents, approval_state, operator_uid, remarks, created_at, updated_at
) VALUES (
    'PARTNER_MDF_VOUCHERS-09-0001', 't_hist_001', '2025-01', 'PRO', 'CN-NORTH', 'CENTS',
    39800, 37547, 2253, 0, 0, 'ARCHIVED', 'dw_loader_2025',
    '历史数仓归档快照批次 #9-1', '2025-01-28T16:00:00Z', '2025-01-28T16:00:00Z'
);
INSERT OR IGNORE INTO hist_partner_mdf_vouchers_master (
    voucher_no, tenant_id, period_key, plan_code, region_code, currency_mode,
    gross_amount_cents, net_amount_cents, tax_amount_cents, promo_offset_cents,
    manual_adj_cents, approval_state, operator_uid, remarks, created_at, updated_at
) VALUES (
    'PARTNER_MDF_VOUCHERS-09-0002', 't_hist_002', '2025-02', 'ENTERPRISE', 'CN-SOUTH', 'CENTS',
    59700, 56321, 3379, 0, 0, 'ARCHIVED', 'dw_loader_2025',
    '历史数仓归档快照批次 #9-2', '2025-02-28T16:00:00Z', '2025-02-28T16:00:00Z'
);
INSERT OR IGNORE INTO hist_partner_mdf_vouchers_master (
    voucher_no, tenant_id, period_key, plan_code, region_code, currency_mode,
    gross_amount_cents, net_amount_cents, tax_amount_cents, promo_offset_cents,
    manual_adj_cents, approval_state, operator_uid, remarks, created_at, updated_at
) VALUES (
    'PARTNER_MDF_VOUCHERS-09-0003', 't_hist_003', '2025-03', 'LEGACY_FLAT_99', 'AP-SG', 'CENTS',
    79600, 75094, 4506, 0, 0, 'ARCHIVED', 'dw_loader_2025',
    '历史数仓归档快照批次 #9-3', '2025-03-28T16:00:00Z', '2025-03-28T16:00:00Z'
);
INSERT OR IGNORE INTO hist_partner_mdf_vouchers_master (
    voucher_no, tenant_id, period_key, plan_code, region_code, currency_mode,
    gross_amount_cents, net_amount_cents, tax_amount_cents, promo_offset_cents,
    manual_adj_cents, approval_state, operator_uid, remarks, created_at, updated_at
) VALUES (
    'PARTNER_MDF_VOUCHERS-09-0004', 't_hist_004', '2025-04', 'STARTER', 'CN-EAST', 'CENTS',
    99500, 93868, 5632, 0, 0, 'ARCHIVED', 'dw_loader_2025',
    '历史数仓归档快照批次 #9-4', '2025-04-28T16:00:00Z', '2025-04-28T16:00:00Z'
);
INSERT OR IGNORE INTO hist_partner_mdf_vouchers_master (
    voucher_no, tenant_id, period_key, plan_code, region_code, currency_mode,
    gross_amount_cents, net_amount_cents, tax_amount_cents, promo_offset_cents,
    manual_adj_cents, approval_state, operator_uid, remarks, created_at, updated_at
) VALUES (
    'PARTNER_MDF_VOUCHERS-09-0005', 't_hist_005', '2025-05', 'PRO', 'CN-NORTH', 'CENTS',
    19900, 18774, 1126, 0, 0, 'ARCHIVED', 'dw_loader_2025',
    '历史数仓归档快照批次 #9-5', '2025-05-28T16:00:00Z', '2025-05-28T16:00:00Z'
);
INSERT OR IGNORE INTO hist_partner_mdf_vouchers_master (
    voucher_no, tenant_id, period_key, plan_code, region_code, currency_mode,
    gross_amount_cents, net_amount_cents, tax_amount_cents, promo_offset_cents,
    manual_adj_cents, approval_state, operator_uid, remarks, created_at, updated_at
) VALUES (
    'PARTNER_MDF_VOUCHERS-09-0006', 't_hist_006', '2025-06', 'ENTERPRISE', 'CN-SOUTH', 'CENTS',
    39800, 37547, 2253, 0, 0, 'ARCHIVED', 'dw_loader_2025',
    '历史数仓归档快照批次 #9-6', '2025-06-28T16:00:00Z', '2025-06-28T16:00:00Z'
);
INSERT OR IGNORE INTO hist_partner_mdf_vouchers_master (
    voucher_no, tenant_id, period_key, plan_code, region_code, currency_mode,
    gross_amount_cents, net_amount_cents, tax_amount_cents, promo_offset_cents,
    manual_adj_cents, approval_state, operator_uid, remarks, created_at, updated_at
) VALUES (
    'PARTNER_MDF_VOUCHERS-09-0007', 't_hist_007', '2025-07', 'LEGACY_FLAT_99', 'AP-SG', 'CENTS',
    59700, 56321, 3379, 0, 0, 'ARCHIVED', 'dw_loader_2025',
    '历史数仓归档快照批次 #9-7', '2025-07-28T16:00:00Z', '2025-07-28T16:00:00Z'
);
INSERT OR IGNORE INTO hist_partner_mdf_vouchers_master (
    voucher_no, tenant_id, period_key, plan_code, region_code, currency_mode,
    gross_amount_cents, net_amount_cents, tax_amount_cents, promo_offset_cents,
    manual_adj_cents, approval_state, operator_uid, remarks, created_at, updated_at
) VALUES (
    'PARTNER_MDF_VOUCHERS-09-0008', 't_hist_008', '2025-08', 'STARTER', 'CN-EAST', 'CENTS',
    79600, 75094, 4506, 0, 0, 'ARCHIVED', 'dw_loader_2025',
    '历史数仓归档快照批次 #9-8', '2025-08-28T16:00:00Z', '2025-08-28T16:00:00Z'
);
INSERT OR IGNORE INTO hist_partner_mdf_vouchers_master (
    voucher_no, tenant_id, period_key, plan_code, region_code, currency_mode,
    gross_amount_cents, net_amount_cents, tax_amount_cents, promo_offset_cents,
    manual_adj_cents, approval_state, operator_uid, remarks, created_at, updated_at
) VALUES (
    'PARTNER_MDF_VOUCHERS-09-0009', 't_hist_009', '2025-09', 'PRO', 'CN-NORTH', 'CENTS',
    99500, 93868, 5632, 0, 0, 'ARCHIVED', 'dw_loader_2025',
    '历史数仓归档快照批次 #9-9', '2025-09-28T16:00:00Z', '2025-09-28T16:00:00Z'
);
INSERT OR IGNORE INTO hist_partner_mdf_vouchers_master (
    voucher_no, tenant_id, period_key, plan_code, region_code, currency_mode,
    gross_amount_cents, net_amount_cents, tax_amount_cents, promo_offset_cents,
    manual_adj_cents, approval_state, operator_uid, remarks, created_at, updated_at
) VALUES (
    'PARTNER_MDF_VOUCHERS-09-0010', 't_hist_010', '2025-01', 'ENTERPRISE', 'CN-SOUTH', 'CENTS',
    19900, 18774, 1126, 0, 0, 'ARCHIVED', 'dw_loader_2025',
    '历史数仓归档快照批次 #9-10', '2025-01-28T16:00:00Z', '2025-01-28T16:00:00Z'
);
INSERT OR IGNORE INTO hist_partner_mdf_vouchers_master (
    voucher_no, tenant_id, period_key, plan_code, region_code, currency_mode,
    gross_amount_cents, net_amount_cents, tax_amount_cents, promo_offset_cents,
    manual_adj_cents, approval_state, operator_uid, remarks, created_at, updated_at
) VALUES (
    'PARTNER_MDF_VOUCHERS-09-0011', 't_hist_011', '2025-02', 'LEGACY_FLAT_99', 'AP-SG', 'CENTS',
    39800, 37547, 2253, 0, 0, 'ARCHIVED', 'dw_loader_2025',
    '历史数仓归档快照批次 #9-11', '2025-02-28T16:00:00Z', '2025-02-28T16:00:00Z'
);
INSERT OR IGNORE INTO hist_partner_mdf_vouchers_master (
    voucher_no, tenant_id, period_key, plan_code, region_code, currency_mode,
    gross_amount_cents, net_amount_cents, tax_amount_cents, promo_offset_cents,
    manual_adj_cents, approval_state, operator_uid, remarks, created_at, updated_at
) VALUES (
    'PARTNER_MDF_VOUCHERS-09-0012', 't_hist_012', '2025-03', 'STARTER', 'CN-EAST', 'CENTS',
    59700, 56321, 3379, 0, 0, 'ARCHIVED', 'dw_loader_2025',
    '历史数仓归档快照批次 #9-12', '2025-03-28T16:00:00Z', '2025-03-28T16:00:00Z'
);
INSERT OR IGNORE INTO hist_partner_mdf_vouchers_master (
    voucher_no, tenant_id, period_key, plan_code, region_code, currency_mode,
    gross_amount_cents, net_amount_cents, tax_amount_cents, promo_offset_cents,
    manual_adj_cents, approval_state, operator_uid, remarks, created_at, updated_at
) VALUES (
    'PARTNER_MDF_VOUCHERS-09-0013', 't_hist_013', '2025-04', 'PRO', 'CN-NORTH', 'CENTS',
    79600, 75094, 4506, 0, 0, 'ARCHIVED', 'dw_loader_2025',
    '历史数仓归档快照批次 #9-13', '2025-04-28T16:00:00Z', '2025-04-28T16:00:00Z'
);
INSERT OR IGNORE INTO hist_partner_mdf_vouchers_master (
    voucher_no, tenant_id, period_key, plan_code, region_code, currency_mode,
    gross_amount_cents, net_amount_cents, tax_amount_cents, promo_offset_cents,
    manual_adj_cents, approval_state, operator_uid, remarks, created_at, updated_at
) VALUES (
    'PARTNER_MDF_VOUCHERS-09-0014', 't_hist_014', '2025-05', 'ENTERPRISE', 'CN-SOUTH', 'CENTS',
    99500, 93868, 5632, 0, 0, 'ARCHIVED', 'dw_loader_2025',
    '历史数仓归档快照批次 #9-14', '2025-05-28T16:00:00Z', '2025-05-28T16:00:00Z'
);
INSERT OR IGNORE INTO hist_partner_mdf_vouchers_master (
    voucher_no, tenant_id, period_key, plan_code, region_code, currency_mode,
    gross_amount_cents, net_amount_cents, tax_amount_cents, promo_offset_cents,
    manual_adj_cents, approval_state, operator_uid, remarks, created_at, updated_at
) VALUES (
    'PARTNER_MDF_VOUCHERS-09-0015', 't_hist_015', '2025-06', 'LEGACY_FLAT_99', 'AP-SG', 'CENTS',
    19900, 18774, 1126, 0, 0, 'ARCHIVED', 'dw_loader_2025',
    '历史数仓归档快照批次 #9-15', '2025-06-28T16:00:00Z', '2025-06-28T16:00:00Z'
);
INSERT OR IGNORE INTO hist_partner_mdf_vouchers_master (
    voucher_no, tenant_id, period_key, plan_code, region_code, currency_mode,
    gross_amount_cents, net_amount_cents, tax_amount_cents, promo_offset_cents,
    manual_adj_cents, approval_state, operator_uid, remarks, created_at, updated_at
) VALUES (
    'PARTNER_MDF_VOUCHERS-09-0016', 't_hist_016', '2025-07', 'STARTER', 'CN-EAST', 'CENTS',
    39800, 37547, 2253, 0, 0, 'ARCHIVED', 'dw_loader_2025',
    '历史数仓归档快照批次 #9-16', '2025-07-28T16:00:00Z', '2025-07-28T16:00:00Z'
);
INSERT OR IGNORE INTO hist_partner_mdf_vouchers_master (
    voucher_no, tenant_id, period_key, plan_code, region_code, currency_mode,
    gross_amount_cents, net_amount_cents, tax_amount_cents, promo_offset_cents,
    manual_adj_cents, approval_state, operator_uid, remarks, created_at, updated_at
) VALUES (
    'PARTNER_MDF_VOUCHERS-09-0017', 't_hist_017', '2025-08', 'PRO', 'CN-NORTH', 'CENTS',
    59700, 56321, 3379, 0, 0, 'ARCHIVED', 'dw_loader_2025',
    '历史数仓归档快照批次 #9-17', '2025-08-28T16:00:00Z', '2025-08-28T16:00:00Z'
);
INSERT OR IGNORE INTO hist_partner_mdf_vouchers_master (
    voucher_no, tenant_id, period_key, plan_code, region_code, currency_mode,
    gross_amount_cents, net_amount_cents, tax_amount_cents, promo_offset_cents,
    manual_adj_cents, approval_state, operator_uid, remarks, created_at, updated_at
) VALUES (
    'PARTNER_MDF_VOUCHERS-09-0018', 't_hist_018', '2025-09', 'ENTERPRISE', 'CN-SOUTH', 'CENTS',
    79600, 75094, 4506, 0, 0, 'ARCHIVED', 'dw_loader_2025',
    '历史数仓归档快照批次 #9-18', '2025-09-28T16:00:00Z', '2025-09-28T16:00:00Z'
);
INSERT OR IGNORE INTO hist_partner_mdf_vouchers_master (
    voucher_no, tenant_id, period_key, plan_code, region_code, currency_mode,
    gross_amount_cents, net_amount_cents, tax_amount_cents, promo_offset_cents,
    manual_adj_cents, approval_state, operator_uid, remarks, created_at, updated_at
) VALUES (
    'PARTNER_MDF_VOUCHERS-09-0019', 't_hist_019', '2025-01', 'LEGACY_FLAT_99', 'AP-SG', 'CENTS',
    99500, 93868, 5632, 0, 0, 'ARCHIVED', 'dw_loader_2025',
    '历史数仓归档快照批次 #9-19', '2025-01-28T16:00:00Z', '2025-01-28T16:00:00Z'
);
INSERT OR IGNORE INTO hist_partner_mdf_vouchers_master (
    voucher_no, tenant_id, period_key, plan_code, region_code, currency_mode,
    gross_amount_cents, net_amount_cents, tax_amount_cents, promo_offset_cents,
    manual_adj_cents, approval_state, operator_uid, remarks, created_at, updated_at
) VALUES (
    'PARTNER_MDF_VOUCHERS-09-0020', 't_hist_020', '2025-02', 'STARTER', 'CN-EAST', 'CENTS',
    19900, 18774, 1126, 0, 0, 'ARCHIVED', 'dw_loader_2025',
    '历史数仓归档快照批次 #9-20', '2025-02-28T16:00:00Z', '2025-02-28T16:00:00Z'
);
INSERT OR IGNORE INTO hist_partner_mdf_vouchers_master (
    voucher_no, tenant_id, period_key, plan_code, region_code, currency_mode,
    gross_amount_cents, net_amount_cents, tax_amount_cents, promo_offset_cents,
    manual_adj_cents, approval_state, operator_uid, remarks, created_at, updated_at
) VALUES (
    'PARTNER_MDF_VOUCHERS-09-0021', 't_hist_021', '2025-03', 'PRO', 'CN-NORTH', 'CENTS',
    39800, 37547, 2253, 0, 0, 'ARCHIVED', 'dw_loader_2025',
    '历史数仓归档快照批次 #9-21', '2025-03-28T16:00:00Z', '2025-03-28T16:00:00Z'
);
INSERT OR IGNORE INTO hist_partner_mdf_vouchers_master (
    voucher_no, tenant_id, period_key, plan_code, region_code, currency_mode,
    gross_amount_cents, net_amount_cents, tax_amount_cents, promo_offset_cents,
    manual_adj_cents, approval_state, operator_uid, remarks, created_at, updated_at
) VALUES (
    'PARTNER_MDF_VOUCHERS-09-0022', 't_hist_022', '2025-04', 'ENTERPRISE', 'CN-SOUTH', 'CENTS',
    59700, 56321, 3379, 0, 0, 'ARCHIVED', 'dw_loader_2025',
    '历史数仓归档快照批次 #9-22', '2025-04-28T16:00:00Z', '2025-04-28T16:00:00Z'
);
INSERT OR IGNORE INTO hist_partner_mdf_vouchers_master (
    voucher_no, tenant_id, period_key, plan_code, region_code, currency_mode,
    gross_amount_cents, net_amount_cents, tax_amount_cents, promo_offset_cents,
    manual_adj_cents, approval_state, operator_uid, remarks, created_at, updated_at
) VALUES (
    'PARTNER_MDF_VOUCHERS-09-0023', 't_hist_023', '2025-05', 'LEGACY_FLAT_99', 'AP-SG', 'CENTS',
    79600, 75094, 4506, 0, 0, 'ARCHIVED', 'dw_loader_2025',
    '历史数仓归档快照批次 #9-23', '2025-05-28T16:00:00Z', '2025-05-28T16:00:00Z'
);
INSERT OR IGNORE INTO hist_partner_mdf_vouchers_master (
    voucher_no, tenant_id, period_key, plan_code, region_code, currency_mode,
    gross_amount_cents, net_amount_cents, tax_amount_cents, promo_offset_cents,
    manual_adj_cents, approval_state, operator_uid, remarks, created_at, updated_at
) VALUES (
    'PARTNER_MDF_VOUCHERS-09-0024', 't_hist_024', '2025-06', 'STARTER', 'CN-EAST', 'CENTS',
    99500, 93868, 5632, 0, 0, 'ARCHIVED', 'dw_loader_2025',
    '历史数仓归档快照批次 #9-24', '2025-06-28T16:00:00Z', '2025-06-28T16:00:00Z'
);
INSERT OR IGNORE INTO hist_partner_mdf_vouchers_master (
    voucher_no, tenant_id, period_key, plan_code, region_code, currency_mode,
    gross_amount_cents, net_amount_cents, tax_amount_cents, promo_offset_cents,
    manual_adj_cents, approval_state, operator_uid, remarks, created_at, updated_at
) VALUES (
    'PARTNER_MDF_VOUCHERS-09-0025', 't_hist_025', '2025-07', 'PRO', 'CN-NORTH', 'CENTS',
    19900, 18774, 1126, 0, 0, 'ARCHIVED', 'dw_loader_2025',
    '历史数仓归档快照批次 #9-25', '2025-07-28T16:00:00Z', '2025-07-28T16:00:00Z'
);
INSERT OR IGNORE INTO hist_partner_mdf_vouchers_master (
    voucher_no, tenant_id, period_key, plan_code, region_code, currency_mode,
    gross_amount_cents, net_amount_cents, tax_amount_cents, promo_offset_cents,
    manual_adj_cents, approval_state, operator_uid, remarks, created_at, updated_at
) VALUES (
    'PARTNER_MDF_VOUCHERS-09-0026', 't_hist_026', '2025-08', 'ENTERPRISE', 'CN-SOUTH', 'CENTS',
    39800, 37547, 2253, 0, 0, 'ARCHIVED', 'dw_loader_2025',
    '历史数仓归档快照批次 #9-26', '2025-08-28T16:00:00Z', '2025-08-28T16:00:00Z'
);
INSERT OR IGNORE INTO hist_partner_mdf_vouchers_master (
    voucher_no, tenant_id, period_key, plan_code, region_code, currency_mode,
    gross_amount_cents, net_amount_cents, tax_amount_cents, promo_offset_cents,
    manual_adj_cents, approval_state, operator_uid, remarks, created_at, updated_at
) VALUES (
    'PARTNER_MDF_VOUCHERS-09-0027', 't_hist_027', '2025-09', 'LEGACY_FLAT_99', 'AP-SG', 'CENTS',
    59700, 56321, 3379, 0, 0, 'ARCHIVED', 'dw_loader_2025',
    '历史数仓归档快照批次 #9-27', '2025-09-28T16:00:00Z', '2025-09-28T16:00:00Z'
);
INSERT OR IGNORE INTO hist_partner_mdf_vouchers_master (
    voucher_no, tenant_id, period_key, plan_code, region_code, currency_mode,
    gross_amount_cents, net_amount_cents, tax_amount_cents, promo_offset_cents,
    manual_adj_cents, approval_state, operator_uid, remarks, created_at, updated_at
) VALUES (
    'PARTNER_MDF_VOUCHERS-09-0028', 't_hist_028', '2025-01', 'STARTER', 'CN-EAST', 'CENTS',
    79600, 75094, 4506, 0, 0, 'ARCHIVED', 'dw_loader_2025',
    '历史数仓归档快照批次 #9-28', '2025-01-28T16:00:00Z', '2025-01-28T16:00:00Z'
);
INSERT OR IGNORE INTO hist_partner_mdf_vouchers_master (
    voucher_no, tenant_id, period_key, plan_code, region_code, currency_mode,
    gross_amount_cents, net_amount_cents, tax_amount_cents, promo_offset_cents,
    manual_adj_cents, approval_state, operator_uid, remarks, created_at, updated_at
) VALUES (
    'PARTNER_MDF_VOUCHERS-09-0029', 't_hist_029', '2025-02', 'PRO', 'CN-NORTH', 'CENTS',
    99500, 93868, 5632, 0, 0, 'ARCHIVED', 'dw_loader_2025',
    '历史数仓归档快照批次 #9-29', '2025-02-28T16:00:00Z', '2025-02-28T16:00:00Z'
);
INSERT OR IGNORE INTO hist_partner_mdf_vouchers_master (
    voucher_no, tenant_id, period_key, plan_code, region_code, currency_mode,
    gross_amount_cents, net_amount_cents, tax_amount_cents, promo_offset_cents,
    manual_adj_cents, approval_state, operator_uid, remarks, created_at, updated_at
) VALUES (
    'PARTNER_MDF_VOUCHERS-09-0030', 't_hist_030', '2025-03', 'ENTERPRISE', 'CN-SOUTH', 'CENTS',
    19900, 18774, 1126, 0, 0, 'ARCHIVED', 'dw_loader_2025',
    '历史数仓归档快照批次 #9-30', '2025-03-28T16:00:00Z', '2025-03-28T16:00:00Z'
);
INSERT OR IGNORE INTO hist_partner_mdf_vouchers_master (
    voucher_no, tenant_id, period_key, plan_code, region_code, currency_mode,
    gross_amount_cents, net_amount_cents, tax_amount_cents, promo_offset_cents,
    manual_adj_cents, approval_state, operator_uid, remarks, created_at, updated_at
) VALUES (
    'PARTNER_MDF_VOUCHERS-09-0031', 't_hist_031', '2025-04', 'LEGACY_FLAT_99', 'AP-SG', 'CENTS',
    39800, 37547, 2253, 0, 0, 'ARCHIVED', 'dw_loader_2025',
    '历史数仓归档快照批次 #9-31', '2025-04-28T16:00:00Z', '2025-04-28T16:00:00Z'
);
INSERT OR IGNORE INTO hist_partner_mdf_vouchers_master (
    voucher_no, tenant_id, period_key, plan_code, region_code, currency_mode,
    gross_amount_cents, net_amount_cents, tax_amount_cents, promo_offset_cents,
    manual_adj_cents, approval_state, operator_uid, remarks, created_at, updated_at
) VALUES (
    'PARTNER_MDF_VOUCHERS-09-0032', 't_hist_032', '2025-05', 'STARTER', 'CN-EAST', 'CENTS',
    59700, 56321, 3379, 0, 0, 'ARCHIVED', 'dw_loader_2025',
    '历史数仓归档快照批次 #9-32', '2025-05-28T16:00:00Z', '2025-05-28T16:00:00Z'
);
INSERT OR IGNORE INTO hist_partner_mdf_vouchers_master (
    voucher_no, tenant_id, period_key, plan_code, region_code, currency_mode,
    gross_amount_cents, net_amount_cents, tax_amount_cents, promo_offset_cents,
    manual_adj_cents, approval_state, operator_uid, remarks, created_at, updated_at
) VALUES (
    'PARTNER_MDF_VOUCHERS-09-0033', 't_hist_033', '2025-06', 'PRO', 'CN-NORTH', 'CENTS',
    79600, 75094, 4506, 0, 0, 'ARCHIVED', 'dw_loader_2025',
    '历史数仓归档快照批次 #9-33', '2025-06-28T16:00:00Z', '2025-06-28T16:00:00Z'
);
INSERT OR IGNORE INTO hist_partner_mdf_vouchers_master (
    voucher_no, tenant_id, period_key, plan_code, region_code, currency_mode,
    gross_amount_cents, net_amount_cents, tax_amount_cents, promo_offset_cents,
    manual_adj_cents, approval_state, operator_uid, remarks, created_at, updated_at
) VALUES (
    'PARTNER_MDF_VOUCHERS-09-0034', 't_hist_034', '2025-07', 'ENTERPRISE', 'CN-SOUTH', 'CENTS',
    99500, 93868, 5632, 0, 0, 'ARCHIVED', 'dw_loader_2025',
    '历史数仓归档快照批次 #9-34', '2025-07-28T16:00:00Z', '2025-07-28T16:00:00Z'
);
INSERT OR IGNORE INTO hist_partner_mdf_vouchers_master (
    voucher_no, tenant_id, period_key, plan_code, region_code, currency_mode,
    gross_amount_cents, net_amount_cents, tax_amount_cents, promo_offset_cents,
    manual_adj_cents, approval_state, operator_uid, remarks, created_at, updated_at
) VALUES (
    'PARTNER_MDF_VOUCHERS-09-0035', 't_hist_035', '2025-08', 'LEGACY_FLAT_99', 'AP-SG', 'CENTS',
    19900, 18774, 1126, 0, 0, 'ARCHIVED', 'dw_loader_2025',
    '历史数仓归档快照批次 #9-35', '2025-08-28T16:00:00Z', '2025-08-28T16:00:00Z'
);
