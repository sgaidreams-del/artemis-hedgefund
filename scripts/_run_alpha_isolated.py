#!/usr/bin/env python3
"""Run the alpha signal pipeline in its own process.

LightGBM shares a process with torch (FinBERT) and hmmlearn (regime) earlier
in run_pipeline.py's JOBS loop; each bundles its own OpenMP runtime, and the
resulting conflict has been observed to segfault non-deterministically. A
segfault is a process-level signal, not a Python exception, so the JOBS
loop's try/except can't catch it — isolating this job in a subprocess keeps
one native crash from taking down the rest of the daily pipeline.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.core.config import universe  # noqa: E402
from src.strategy.alpha.qlib_model import run_alpha_pipeline  # noqa: E402


def main() -> int:
    tickers = universe()["seed_tickers"]
    count = run_alpha_pipeline(tickers)
    print(json.dumps({"upserted": count}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
