"""Company fundamentals via yfinance. SPEC §4.1."""
from __future__ import annotations

from datetime import date

import yfinance as yf
from psycopg.types.json import Json

from ...core.config import universe
from ...core.db import conn
from ...core.logging import get_logger, log_activity

log = get_logger("fundamentals_collector")


def collect() -> dict:
    tickers = universe()["seed_tickers"]
    today = date.today()
    inserted = 0
    failed = 0
    with conn() as c, c.cursor() as cur:
        for sym in tickers:
            try:
                t = yf.Ticker(sym)
                info = t.info or {}
                cur.execute(
                    """
                    INSERT INTO fundamentals
                      (ticker, asof_date, market_cap, pe_ratio, eps, dividend_yield,
                       revenue_ttm, sector, industry, payload)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (ticker, asof_date) DO UPDATE
                      SET market_cap=EXCLUDED.market_cap,
                          pe_ratio=EXCLUDED.pe_ratio,
                          eps=EXCLUDED.eps,
                          dividend_yield=EXCLUDED.dividend_yield,
                          revenue_ttm=EXCLUDED.revenue_ttm,
                          sector=EXCLUDED.sector,
                          industry=EXCLUDED.industry,
                          payload=EXCLUDED.payload
                    """,
                    (
                        sym, today,
                        info.get("marketCap"),
                        info.get("trailingPE"),
                        info.get("trailingEps"),
                        info.get("dividendYield"),
                        info.get("totalRevenue"),
                        info.get("sector"),
                        info.get("industry"),
                        # Filter to JSON-safe scalars; Json() wrapper required for psycopg3 to adapt to JSONB
                        Json({k: v for k, v in info.items() if isinstance(v, (str, int, float, bool, type(None)))}),
                    ),
                )
                inserted += 1
            except Exception as e:
                log.warning("fundamentals_failed", ticker=sym, err=str(e))
                failed += 1
        c.commit()
    log_activity("fundamentals_collector", "collect", "ok",
                 tickers=len(tickers), inserted=inserted, failed=failed)
    return {"tickers": len(tickers), "inserted": inserted, "failed": failed}
