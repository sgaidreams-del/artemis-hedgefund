#!/usr/bin/env python3
"""Compute and optionally submit today's rebalance orders.

Defaults to a dry run — nothing is submitted to the broker unless you
pass --live. Use --scheduled when called from a LaunchAgent or cron job
(skips the interactive confirmation prompt; --live is implied).

Usage:
    python scripts/run_daily_trade.py                    # preview only
    python scripts/run_daily_trade.py --live             # interactive confirm → submit
    python scripts/run_daily_trade.py --scheduled        # non-interactive; submit live orders
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.execution.daily_trader import run_daily_rebalance  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true",
                        help="Submit real (paper) orders (requires interactive confirmation).")
    parser.add_argument("--scheduled", action="store_true",
                        help="Non-interactive live-trade mode for LaunchAgent/cron use.")
    args = parser.parse_args()

    live = args.live or args.scheduled

    if args.live and not args.scheduled:
        confirmed = input("This will submit real orders to your paper account. Type 'yes' to continue: ")
        if confirmed.strip().lower() != "yes":
            print("Aborted.")
            return 1

    result = run_daily_rebalance(dry_run=not live)
    print(json.dumps(result, indent=2, default=str))

    status = result.get("status", "error")
    # "paused", "halt", "no_scores", "reconciliation_mismatch" are all legitimate
    # non-error outcomes for a scheduled run — don't treat them as failures.
    ok_statuses = {"ok", "paused", "halt", "no_scores", "reconciliation_mismatch", "no_account"}
    return 0 if status in ok_statuses else 1


if __name__ == "__main__":
    sys.exit(main())
