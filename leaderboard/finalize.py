#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一键出榜快捷入口。"""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
cmd = [sys.executable, str(ROOT / "src" / "scoring" / "finalize.py"), *sys.argv[1:]]
raise SystemExit(subprocess.run(cmd).returncode)
