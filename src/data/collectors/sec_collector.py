"""SEC EDGAR collector — 10-K, 10-Q, 8-K, Form 4. SPEC §4.1.

STATUS: STUB. Implement after Phase 1 core collectors are stable.
"""
from __future__ import annotations

from ...core.logging import get_logger, log_activity

log = get_logger("sec_collector")


def collect_recent() -> dict:
    log.info("not_implemented", reason="sec-edgar-downloader not wired yet")
    log_activity("sec_collector", "collect_recent", "skipped", reason="not_implemented")
    return {"status": "stub"}

# TODO when implementing:
# - sec_edgar_downloader.Downloader(...)
# - dl.get("10-K", ticker, after=last_check_date)
# - dl.get("8-K", ...) — earnings, material events
# - dl.get("4", ...) — insider transactions
# - Store filings on disk; index metadata in PostgreSQL (sec_filings table — add to schema)
