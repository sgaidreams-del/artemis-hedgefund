"""Corporate actions handler. SPEC §4.4.

STATUS: STUB scaffold. Implement after Polygon API key is provided.
"""
from __future__ import annotations

from ...core.logging import get_logger, log_activity

log = get_logger("corporate_actions")


def run() -> dict:
    log.info("not_implemented", reason="awaiting Polygon API key + design review")
    log_activity("corporate_actions", "run", "skipped", reason="not_implemented")
    return {"status": "stub"}

# TODO when implementing (HIGH PRIORITY — splits silently corrupt indicators):
# - Polygon: /v3/reference/splits, /v3/reference/dividends
# - For each new action since last_check:
#     - Apply retroactive split adjustment to ohlcv_daily
#     - Recompute affected features in feature_store
#     - Update positions table for held tickers
#     - Insert into corporate_actions audit table
# - Cross-check with yfinance.Ticker(sym).splits / .dividends
