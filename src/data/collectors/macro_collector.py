"""FRED macro indicator collector. SPEC §4.1."""
from __future__ import annotations

from fredapi import Fred

from ...core.config import env
from ...core.db import conn
from ...core.logging import get_logger, log_activity

log = get_logger("macro_collector")

# Core macro series (expandable; AutoResearch can add more)
SERIES = [
    "DGS10",       # 10-Year Treasury Constant Maturity Rate
    "DGS2",        # 2-Year Treasury
    "DFF",         # Federal Funds Effective Rate
    "T10Y2Y",      # 10Y-2Y spread (recession proxy)
    "VIXCLS",      # CBOE Volatility Index
    "CPIAUCSL",    # CPI (urban consumers)
    "UNRATE",      # Unemployment rate
    "DCOILWTICO",  # Crude oil
    "DTWEXBGS",    # USD broad index
    "ICSA",        # Initial jobless claims
]


def collect() -> dict:
    api_key = env("FRED_API_KEY", required=True)
    fred = Fred(api_key=api_key)
    inserted = 0
    failed = 0
    with conn() as c, c.cursor() as cur:
        for sid in SERIES:
            try:
                s = fred.get_series_latest_release(sid)
                if s is None or s.empty:
                    continue
                for d, v in s.tail(60).items():  # most recent 60 obs
                    if v != v:  # NaN
                        continue
                    cur.execute(
                        """
                        INSERT INTO macro_indicators (series_id, date, value)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (series_id, date) DO UPDATE
                          SET value=EXCLUDED.value
                        """,
                        (sid, d.date(), float(v)),
                    )
                    inserted += 1
            except Exception as e:
                log.warning("fred_series_failed", series=sid, err=str(e))
                failed += 1
        c.commit()
    log_activity("macro_collector", "collect", "ok", series=len(SERIES),
                 inserted=inserted, failed=failed)
    return {"series": len(SERIES), "inserted": inserted, "failed": failed}
