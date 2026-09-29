"""Price collector — Alpaca primary, Polygon fallback. SPEC §4.1."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Iterable

from alpaca.data.enums import DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

from ...core.config import env, universe
from ...core.db import conn
from ...core.logging import get_logger, log_activity

log = get_logger("price_collector")


def _alpaca_client() -> StockHistoricalDataClient:
    return StockHistoricalDataClient(
        api_key=env("ALPACA_API_KEY", required=True),
        secret_key=env("ALPACA_API_SECRET", required=True),
    )


def collect_eod(tickers: Iterable[str] | None = None, lookback_days: int = 5) -> dict:
    """Collect end-of-day OHLCV bars for the given tickers (defaults to seed universe).

    Idempotent — upsert on (ticker, date).
    """
    tickers = list(tickers) if tickers else universe()["seed_tickers"]
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=lookback_days)

    client = _alpaca_client()
    req = StockBarsRequest(
        symbol_or_symbols=tickers,
        timeframe=TimeFrame.Day,
        start=start,
        end=end,
        feed=DataFeed.IEX,  # free-tier feed; SIP requires a paid subscription
    )
    bars = client.get_stock_bars(req)
    inserted = 0
    skipped = 0
    with conn() as c, c.cursor() as cur:
        for sym, bar_list in bars.data.items():
            for b in bar_list:
                try:
                    cur.execute(
                        """
                        INSERT INTO ohlcv_daily (ticker, date, open, high, low, close, volume, adj_close)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (ticker, date) DO UPDATE
                          SET open=EXCLUDED.open,
                              high=EXCLUDED.high,
                              low=EXCLUDED.low,
                              close=EXCLUDED.close,
                              volume=EXCLUDED.volume,
                              adj_close=EXCLUDED.adj_close
                        """,
                        (
                            sym,
                            b.timestamp.date(),
                            float(b.open),
                            float(b.high),
                            float(b.low),
                            float(b.close),
                            int(b.volume),
                            float(b.close),  # close as adj_close until corp actions handler runs
                        ),
                    )
                    inserted += 1
                except Exception as e:
                    log.warning("insert_failed", ticker=sym, date=str(b.timestamp.date()), err=str(e))
                    skipped += 1
        c.commit()
    log.info("eod_collected", tickers=len(tickers), rows=inserted, skipped=skipped)
    log_activity("price_collector", "collect_eod", "ok", tickers=len(tickers), rows=inserted)
    return {"tickers": len(tickers), "rows": inserted, "skipped": skipped}


def collect_intraday(tickers: Iterable[str] | None = None, lookback_minutes: int = 15) -> dict:
    """Collect 1-minute bars (only run during market hours; scheduler enforces)."""
    tickers = list(tickers) if tickers else universe()["seed_tickers"]
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=lookback_minutes)
    client = _alpaca_client()
    req = StockBarsRequest(
        symbol_or_symbols=tickers,
        timeframe=TimeFrame.Minute,
        start=start,
        end=end,
        feed=DataFeed.IEX,  # free-tier feed; SIP requires a paid subscription
    )
    bars = client.get_stock_bars(req)
    inserted = 0
    with conn() as c, c.cursor() as cur:
        for sym, bar_list in bars.data.items():
            for b in bar_list:
                cur.execute(
                    """
                    INSERT INTO ohlcv_1m (ticker, ts, open, high, low, close, volume)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (ticker, ts) DO NOTHING
                    """,
                    (sym, b.timestamp, float(b.open), float(b.high), float(b.low),
                     float(b.close), int(b.volume)),
                )
                inserted += 1
        c.commit()
    log_activity("price_collector", "collect_intraday", "ok", tickers=len(tickers), rows=inserted)
    return {"tickers": len(tickers), "rows": inserted}


def backfill(tickers: Iterable[str] | None = None, years: int = 5) -> dict:
    """One-time historical backfill. Use carefully — large data volumes."""
    tickers = list(tickers) if tickers else universe()["seed_tickers"]
    end = date.today()
    start = end - timedelta(days=365 * years)
    log.info("backfill_starting", tickers=len(tickers), years=years, start=str(start))
    client = _alpaca_client()
    req = StockBarsRequest(
        symbol_or_symbols=tickers,
        timeframe=TimeFrame.Day,
        start=start,
        end=end,
        feed=DataFeed.IEX,  # free-tier feed; SIP requires a paid subscription
    )
    bars = client.get_stock_bars(req)
    total = 0
    with conn() as c, c.cursor() as cur:
        for sym, bar_list in bars.data.items():
            for b in bar_list:
                cur.execute(
                    """
                    INSERT INTO ohlcv_daily (ticker, date, open, high, low, close, volume, adj_close)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (ticker, date) DO NOTHING
                    """,
                    (sym, b.timestamp.date(), float(b.open), float(b.high), float(b.low),
                     float(b.close), int(b.volume), float(b.close)),
                )
                total += 1
        c.commit()
    log_activity("price_collector", "backfill", "ok", tickers=len(tickers), rows=total, years=years)
    return {"tickers": len(tickers), "rows": total, "years": years}
