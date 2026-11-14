# -*- coding: utf-8 -*-
"""v3 声明式资费规则 DSL 编译器与求值引擎（架构组实验代码，未挂载生产套餐表）。
支持四种计价模型原语：
- GRADUATED_MARGINAL : 边际超额累进阶梯（云策现行生产标准）
- VOLUME_ALL_UNITS   : 全量单价回溯阶梯（仅用于竞品对比沙盘）
- STAIRSTEP_BAND     : 固定包段一口价阶梯
- BLOCK_PACKAGE      : 每 N 次资源包向上取整计费
"""
import math
from typing import Any, Dict, List, Optional, Tuple


class V3TariffDSLEvaluator:
    @staticmethod
    def parse_dsl_expression(expr: str) -> Dict[str, Any]:
        """解析形如 'GRADUATED_MARGINAL(included=50000; 50000@2, inf@1)' 的资费公式字符串。"""
        raw = (expr or "").strip()
        if "(" not in raw or not raw.endswith(")"):
            raise SyntaxError(f"Malformed tariff DSL: {raw}")
        mode, inner = raw[:-1].split("(", 1)
        mode = mode.strip().upper()
        parts = [p.strip() for p in inner.split(";") if p.strip()]
        if len(parts) != 2 or not parts[0].startswith("included="):
            raise SyntaxError(f"Tariff DSL missing included= header: {raw}")

        included = int(parts[0].split("=", 1)[1].strip())
        tiers: List[Tuple[Optional[int], int]] = []
        for token in parts[1].split(","):
            tok = token.strip()
            if not tok:
                continue
            cap_s, price_s = [x.strip() for x in tok.split("@", 1)]
            cap = None if cap_s.lower() in ("inf", "none", "*") else int(cap_s)
            tiers.append((cap, int(price_s)))

        if not tiers:
            raise SyntaxError("Tariff DSL requires at least one tier")
        return {"mode": mode, "included": included, "tiers": tiers}

    @classmethod
    def evaluate(cls, parsed_spec: Dict[str, Any], usage_units: int) -> Dict[str, Any]:
        mode = parsed_spec["mode"]
        included = int(parsed_spec["included"])
        tiers: List[Tuple[Optional[int], int]] = parsed_spec["tiers"]
        overage = max(0, int(usage_units) - included)

        if overage == 0:
            return {"mode": mode, "overage_units": 0, "fee_cents": 0}

        if mode == "GRADUATED_MARGINAL":
            rem = overage
            fee = 0
            for cap, price in tiers:
                if rem <= 0:
                    break
                take = rem if cap is None else min(rem, cap)
                fee += take * price
                rem -= take
            return {"mode": mode, "overage_units": overage, "fee_cents": fee}

        if mode == "VOLUME_ALL_UNITS":
            chosen_price = tiers[-1][1]
            running_bound = 0
            for cap, price in tiers:
                if cap is None:
                    chosen_price = price
                    break
                running_bound += cap
                if overage <= running_bound:
                    chosen_price = price
                    break
            return {"mode": mode, "overage_units": overage, "fee_cents": overage * chosen_price}

        if mode == "STAIRSTEP_BAND":
            running_bound = 0
            for cap, flat_band_cents in tiers:
                if cap is None:
                    return {"mode": mode, "overage_units": overage, "fee_cents": flat_band_cents}
                running_bound += cap
                if overage <= running_bound:
                    return {"mode": mode, "overage_units": overage, "fee_cents": flat_band_cents}
            return {"mode": mode, "overage_units": overage, "fee_cents": tiers[-1][1]}

        if mode == "BLOCK_PACKAGE":
            block_size = max(1, int(tiers[0][0] or 1000))
            block_price = int(tiers[0][1])
            packs = int(math.ceil(overage / float(block_size)))
            return {"mode": mode, "overage_units": overage, "packs": packs, "fee_cents": packs * block_price}

        raise ValueError(f"Unsupported tariff DSL mode: {mode}")
