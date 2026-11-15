#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v4.0 参考黄金补丁总控入口（仅供评测作者内部自检校准，严禁泄露至选手沙盒）。"""
import argparse
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from _db_repair import repair_database
from _patches_d1_d4 import (
    apply_d1_metering_pricing,
    apply_d2_wallet_settlement,
    apply_d3_treasury_fx,
    apply_d4_fapiao_reconcile,
)
from _patches_d5_d7 import (
    apply_d5_gl_revrec,
    apply_d6_partner_dunning_sod,
    apply_d7_security_export_ui,
)
from _tests_and_report import write_tests_and_report

DOMAIN_HANDLERS = {
    "D1": apply_d1_metering_pricing,
    "D2": apply_d2_wallet_settlement,
    "D3": apply_d3_treasury_fx,
    "D4": apply_d4_fapiao_reconcile,
    "D5": apply_d5_gl_revrec,
    "D6": apply_d6_partner_dunning_sod,
    "D7": apply_d7_security_export_ui,
}


def apply_golden_patch(
    sandbox_dir: Path,
    domains: list[str] | None = None,
    with_db_repair: bool = True,
    with_tests_and_report: bool = True,
) -> None:
    target_domains = domains if domains else list(DOMAIN_HANDLERS.keys())
    for d in target_domains:
        key = d.strip().upper()
        if key not in DOMAIN_HANDLERS:
            raise ValueError(f"Unknown domain key: {key}")
        DOMAIN_HANDLERS[key](sandbox_dir)

    if with_db_repair:
        repair_database(sandbox_dir)
    if with_tests_and_report:
        write_tests_and_report(sandbox_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply v4.0 golden patch to a sandbox directory")
    parser.add_argument("sandbox", help="Path to target sandbox/<run_id>")
    parser.add_argument("--domains", default="ALL", help="Comma-separated D1..D7 or ALL")
    parser.add_argument("--no-db", action="store_true", help="Skip SQLite dirty data repair")
    parser.add_argument("--no-tests", action="store_true", help="Skip writing regression tests and report")
    args = parser.parse_args()

    sb = Path(args.sandbox).resolve()
    doms = None if args.domains.strip().upper() == "ALL" else [x.strip() for x in args.domains.split(",") if x.strip()]
    apply_golden_patch(
        sb,
        domains=doms,
        with_db_repair=not args.no_db,
        with_tests_and_report=not args.no_tests,
    )
    print(f"[GoldenPatch] Successfully applied ({args.domains}) to {sb}")


if __name__ == "__main__":
    main()
