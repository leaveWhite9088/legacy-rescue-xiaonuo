# -*- coding: utf-8 -*-
"""结构化日志工具。"""
import logging
import os

def get_logger(name: str = "yunce") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        level_name = os.environ.get("YUNCE_LOG_LEVEL", "INFO").upper()
        logger.setLevel(getattr(logging, level_name, logging.INFO))
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger
