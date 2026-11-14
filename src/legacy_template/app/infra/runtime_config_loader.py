# -*- coding: utf-8 -*-
"""多源运行期配置读取器：合并环境变量、legacy_settings.ini 与数据库 sys_runtime_configs 动态表。"""
import configparser
import os
from pathlib import Path
import sqlite3
from typing import Any

from app.infra.config import BASE_DIR, FEATURE_FLAGS

_INI_PATH = BASE_DIR / "config" / "legacy_settings.ini"


def _read_ini_fallback(key: str) -> str | None:
    if not _INI_PATH.exists():
        return None
    cp = configparser.ConfigParser()
    cp.read(_INI_PATH, encoding="utf-8")
    for sec in cp.sections():
        if key in cp[sec]:
            return cp[sec][key]
    return None


def get_runtime_bool_flag(conn: sqlite3.Connection, flag_key: str, default: bool = False) -> bool:
    """按优先级读取布尔开关：环境变量 -> sys_runtime_configs 表 -> legacy_settings.ini -> FEATURE_FLAGS。"""
    env_key = f"YUNCE_FLAG_{flag_key.upper()}"
    if env_key in os.environ:
        return os.environ[env_key].strip().lower() in ("1", "true", "yes", "on")

    try:
        row = conn.execute(
            "SELECT config_value FROM sys_runtime_configs WHERE config_key = ?",
            (flag_key,),
        ).fetchone()
        if row is not None and row["config_value"] is not None:
            # 直接转为布尔返回
            return bool(row["config_value"])
    except sqlite3.OperationalError:
        pass

    ini_val = _read_ini_fallback(flag_key)
    if ini_val is not None:
        return ini_val.strip().lower() in ("1", "true", "yes", "on")

    raw_mem: Any = FEATURE_FLAGS.get(flag_key, default)
    return bool(raw_mem)
