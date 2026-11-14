# -*- coding: utf-8 -*-
"""2026 Q3 架构组启动的第三代计费流水线重构实验包 (v3 Experimental Pipeline)。
当前状态：灰度开关 ENABLE_V3_BILLING_PIPELINE 默认关闭（False）。
原因：v3 尚未完成 2024 ACTIVE_LEGACY 老合同、大客户保底协议及价外税引擎适配，仅开启只读影子比对器 (shadow_comparator)。
"""
