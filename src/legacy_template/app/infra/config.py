# -*- coding: utf-8 -*-
"""云策账务中心全局配置、特性灰度开关、套餐阶梯表、税率档案、科目映射与催收策略常量。"""
import os
from pathlib import Path
from typing import Any, Dict

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB_PATH = str(BASE_DIR / "data" / "yunce_billing.db")
DB_PATH = os.environ.get("YUNCE_DB_PATH", DEFAULT_DB_PATH)
ADMIN_API_KEY = os.environ.get("YUNCE_ADMIN_KEY", "yc-admin-secret-2026")
OPS_INTERNAL_TOKEN = os.environ.get("YUNCE_OPS_TOKEN", "yc-ops-readonly-2025")
WEBHOOK_SIGNING_SECRET = os.environ.get("YUNCE_WEBHOOK_SECRET", "whsec_yunce_internal_2026")
EXPORT_DIR = str(BASE_DIR / "data" / "exports")

CACHE_TTL_SECONDS = 300
RATE_LIMIT_WINDOW_SECONDS = 60

# 历史演进遗留的跨代灰度与运行期开关（部分开关由 2024->2025->2026 三轮架构迭代积累）
FEATURE_FLAGS: Dict[str, Any] = {
    # 2026 Q3 第三代计费流水线实验开关（尚未支持老租户、企业保底及价外税，生产严禁直接开启！）
    "ENABLE_V3_BILLING_PIPELINE": False,
    # 只读影子比对器抽样开关（仅在诊断接口只读调用，不写库）
    "ENABLE_V3_SHADOW_COMPARATOR": True,
    # 2024 v1 异构存量老租户桥接开关（服务 15 家 ACTIVE_LEGACY 制造业老客户，禁止关闭）
    "ENABLE_LEGACY_V1_COMPAT_BRIDGE": True,
    # 网关响应错误详情回显开关
    "VERBOSE_500_DIAGNOSTICS": True,
    # 双写旧版内存配额模拟器（历史兼容开关）
    "SYNC_V1_MEMCACHED_QUOTA_SLAB": True,
    # 金税四期电子专票单张限额自动拆票（默认单张上限 100,000.00 元 = 10,000,000 分）
    "FAPIAO_AUTO_SPLIT_SHEET": True,
    # 大额手工调账与退费双人复核阈值（5,000.00 元 = 500,000 分）
    "APPROVAL_DUAL_SIGN_THRESHOLD_CENTS": 500_000,
    # 催收工单外呼与短信干跑保护
    "DUNNING_OUTBOUND_DRY_RUN": True,
    # 慢请求审计阈值（毫秒）
    "SLOW_HTTP_WARN_MS": 200,
}

# 套餐定义：所有金额均以“分 (cents)”为单位
# 超额计费统一采用超额累进阶梯 (Progressive Marginal Tiering)
PLANS: Dict[str, Dict[str, Any]] = {
    "STARTER": {
        "code": "STARTER",
        "name": "基础版",
        "monthly_fee_cents": 19900,       # 199.00 元
        "included_quota": 10000,          # 含 10,000 次调用
        "burst_limit_per_min": 600,
        "sla_target_bps": 9950,           # 99.50%
        "overage_tiers": [
            (10000, 3),                   # 超额 1 ~ 10,000 次：3 分/次
            (40000, 2),                   # 超额 10,001 ~ 50,000 次：2 分/次
            (None, 1),                    # 超额 > 50,000 次：1 分/次
        ],
    },
    "PRO": {
        "code": "PRO",
        "name": "专业版",
        "monthly_fee_cents": 59900,       # 599.00 元
        "included_quota": 50000,          # 含 50,000 次调用
        "burst_limit_per_min": 2400,
        "sla_target_bps": 9990,           # 99.90%
        "overage_tiers": [
            (50000, 2),                   # 超额 1 ~ 50,000 次：2 分/次
            (None, 1),                    # 超额 > 50,000 次：1 分/次
        ],
    },
    "ENTERPRISE": {
        "code": "ENTERPRISE",
        "name": "企业版",
        "monthly_fee_cents": 199900,      # 1,999.00 元
        "included_quota": 300000,         # 含 300,000 次调用
        "burst_limit_per_min": 12000,
        "sla_target_bps": 9995,           # 99.95%
        "overage_tiers": [
            (200000, 1),
            (None, 1),
        ],
    },
    # 2024 年早期存量包干合同（仅限 ACTIVE_LEGACY 老客户续期，禁止新签）
    "LEGACY_FLAT_99": {
        "code": "LEGACY_FLAT_99",
        "name": "老版本包干99",
        "monthly_fee_cents": 9900,
        "included_quota": 20000,
        "burst_limit_per_min": 1000,
        "sla_target_bps": 9900,
        "is_legacy": True,
        "overage_tiers": [
            (None, 2),
        ],
    },
}

# 税率规则：rate_bps 为万分比，inclusive 表示套餐标价是否已含税
TAX_PROFILES: Dict[str, Dict[str, Any]] = {
    "CN_VAT_6_INCLUSIVE": {
        "code": "CN_VAT_6_INCLUSIVE",
        "rate_bps": 600,
        "inclusive": True,
        "fapiao_eligible": True,
        "label": "中国增值税6%(含税价)",
    },
    "CN_VAT_6_EXCLUSIVE": {
        "code": "CN_VAT_6_EXCLUSIVE",
        "rate_bps": 600,
        "inclusive": False,
        "fapiao_eligible": True,
        "label": "中国增值税6%(价外税)",
    },
    "SG_GST_9_EXCLUSIVE": {
        "code": "SG_GST_9_EXCLUSIVE",
        "rate_bps": 900,
        "inclusive": False,
        "fapiao_eligible": False,
        "label": "新加坡GST 9%(价外税)",
    },
    "EXEMPT": {
        "code": "EXEMPT",
        "rate_bps": 0,
        "inclusive": True,
        "fapiao_eligible": True,
        "label": "免税/跨境零税率",
    },
}

# 渠道代理商返佣阶梯配置
PARTNER_TIERS: Dict[str, Dict[str, int]] = {
    "SILVER": {"rate_bps": 800, "min_quarterly_cents": 0},          # 8%
    "GOLD": {"rate_bps": 1200, "min_quarterly_cents": 500000},      # 12%
    "PLATINUM": {"rate_bps": 1500, "min_quarterly_cents": 2000000}, # 15%
}

LATE_FEE_RATE_BPS = 500

FAPIAO_SINGLE_SHEET_MAX_CENTS = 10_000_000

RUNTIME_COMPAT_REGISTRY: Dict[str, Any] = {}

DUNNING_STAGE_POLICY = [
    {"stage": "GRACE", "min_overdue_days": 1, "max_overdue_days": 3, "throttle_pct": 0, "channel": "EMAIL"},
    {"stage": "REMINDER_L1", "min_overdue_days": 4, "max_overdue_days": 7, "throttle_pct": 0, "channel": "SMS_EMAIL"},
    {"stage": "WARNING_L2", "min_overdue_days": 8, "max_overdue_days": 14, "throttle_pct": 30, "channel": "CSM_CALL"},
    {"stage": "RESTRICTED_L3", "min_overdue_days": 15, "max_overdue_days": 30, "throttle_pct": 80, "channel": "LEGAL_LETTER"},
    {"stage": "SUSPENDED", "min_overdue_days": 31, "max_overdue_days": 9999, "throttle_pct": 100, "channel": "COLLECTION_AGENCY"},
]

GL_ACCOUNT_CATALOG = {
    "1122_AR_TRADE": "应收账款-SaaS订阅与计量",
    "1002_CASH_BANK": "银行存款-基本户实收",
    "2203_DEFERRED_WALLET": "合同负债-客户预存现金池",
    "2221_VAT_PAYABLE": "应交税费-应交增值税(销项税额)",
    "6001_REV_SUBSCRIPTION": "主营业务收入-基础订阅费",
    "6001_REV_OVERAGE": "主营业务收入-弹性超额调用",
    "6601_PROMO_SUBSIDY": "销售费用-运营赠送金核销抵扣",
    "6301_LATE_FEE_INCOME": "营业外收入-逾期违约滞纳金",
}
