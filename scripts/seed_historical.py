#!/usr/bin/env python3
"""One-time historical data backfill. SPEC §1.14."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data.collectors.price_collector import backfill  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", type=int, default=5, help="Years of history to fetch")
    parser.add_argument("--tickers", nargs="*", default=None, help="Limit to these tickers")
    args = parser.parse_args()

    print(f"Seeding {args.years} years of daily OHLCV for "
          f"{'seed universe' if not args.tickers else len(args.tickers)} tickers...")
    result = backfill(tickers=args.tickers, years=args.years)
    print(f"✓ {result['rows']} rows inserted across {result['tickers']} tickers")
    return 0


if __name__ == "__main__":
    sys.exit(main())
