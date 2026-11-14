# -*- coding: utf-8 -*-
"""跨国企业客户年报 ESG（范围三 Scope-3 供应链数字算力碳足迹）千瓦时与二氧化碳当量估算附录生成器。"""
from typing import Any, Dict


REGION_GRID_CARBON_GRAMS_PER_KWH: Dict[str, int] = {
    "cn-east-1": 535,
    "cn-north-2": 580,
    "ap-southeast-1": 408,
    "eu-central-1": 310,
}


def estimate_tenant_scope3_compute_emissions(
    standard_api_units: int,
    region_code: str = "cn-east-1",
    pue_x100: int = 122,
) -> Dict[str, Any]:
    """按每万次标准评测调用约耗电 0.18 kWh 及数据中心 PUE 系数估算碳排放克数。"""
    units = max(0, int(standard_api_units))
    it_kwh = (units / 10000.0) * 0.18
    total_kwh = it_kwh * (max(100, int(pue_x100)) / 100.0)
    grid_intensity = REGION_GRID_CARBON_GRAMS_PER_KWH.get(region_code, 535)
    co2e_grams = total_kwh * grid_intensity
    return {
        "region_code": region_code,
        "standard_api_units": units,
        "datacenter_pue": round(pue_x100 / 100.0, 2),
        "estimated_electricity_kwh": round(total_kwh, 3),
        "estimated_co2e_grams": round(co2e_grams, 1),
        "estimated_co2e_kg": round(co2e_grams / 1000.0, 4),
    }
