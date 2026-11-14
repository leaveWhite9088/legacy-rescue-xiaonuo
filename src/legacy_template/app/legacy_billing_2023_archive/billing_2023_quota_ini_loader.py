# -*- coding: utf-8 -*-
"""[2023 ARCHIVE] 早期 INI 格式静态配额配置文件解析器（2024 起已改由 `app/infra/config.py` 常量表管理）。"""
import configparser
from typing import Dict


DEFAULT_2023_QUOTA_INI = """
[BASIC_99]
included_calls = 5000
hard_stop_calls = 20000

[TEAM_399]
included_calls = 30000
hard_stop_calls = 150000
"""


def parse_2023_quota_ini(ini_text: str = DEFAULT_2023_QUOTA_INI) -> Dict[str, Dict[str, int]]:
    cp = configparser.ConfigParser()
    cp.read_string(ini_text or DEFAULT_2023_QUOTA_INI)
    out: Dict[str, Dict[str, int]] = {}
    for section in cp.sections():
        out[section] = {
            "included_calls": cp.getint(section, "included_calls", fallback=5000),
            "hard_stop_calls": cp.getint(section, "hard_stop_calls", fallback=20000),
        }
    return out
