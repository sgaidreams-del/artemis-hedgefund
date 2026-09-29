"""Universe selection. SPEC §4.7.

STATUS: bootstrap version uses seed_tickers. Full filtering by market cap /
volume runs after fundamentals + price history are loaded.
"""
from __future__ import annotations

from datetime import date

from ..core.config import universe as universe_cfg
from ..core.db import conn
from ..core.logging import log_activity


def refresh_daily() -> dict:
    cfg = universe_cfg()
    tickers = cfg["seed_tickers"]  # bootstrap
    today = date.today()
    with conn() as c, c.cursor() as cur:
        for t in tickers:
            cur.execute(
                """
                INSERT INTO universe_daily (date, ticker, eligible, reason)
                VALUES (%s, %s, TRUE, 'seed_bootstrap')
                ON CONFLICT (date, ticker) DO UPDATE SET eligible=TRUE
                """,
                (today, t),
            )
        c.commit()
    log_activity("universe", "refresh_daily", "ok", n_tickers=len(tickers))
    return {"date": str(today), "n_tickers": len(tickers)}
