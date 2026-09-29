#!/usr/bin/env python3
"""Liquidate every open position and cancel every open order.

This is the emergency manual escape hatch — it is never called by the kill
switch, any halt, or any scheduled job. It exists so a human can deliberately
flatten the (paper) book from the terminal. Requires typing 'yes' to confirm.

Usage:
    python scripts/flatten_all.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.execution.broker import flatten_all  # noqa: E402


def main() -> int:
    confirmed = input(
        "This will CANCEL all open orders and CLOSE all open positions on your "
        "paper account. Type 'yes' to continue: "
    )
    if confirmed.strip().lower() != "yes":
        print("Aborted.")
        return 1

    results = flatten_all(confirm=True)
    print(json.dumps(results, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
