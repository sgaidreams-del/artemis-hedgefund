"""Insider transactions via Finnhub (free tier). Feeds insider_signal.

Finnhub's short-interest endpoint returns 403 on the free tier (confirmed
empirically — Finnhub has a history of moving previously-free endpoints to
premium), so this collector only covers insider-transactions.
"""
from __future__ import annotations

from datetime import date, timedelta

import requests

from ...core.config import env, universe
from ...core.db import conn
from ...core.logging import get_logger, log_activity

log = get_logger("finnhub_collector")

BASE_URL = "https://finnhub.io/api/v1/stock/insider-transactions"

# Standard SEC Form 4 codes for genuine open-market trades. Excludes grants (A),
# gifts (G), option exercises (M), tax withholding (F), etc. — those don't
# reflect buy/sell sentiment the way a real market purchase or sale does.
_BUY_CODES = {"P"}
_SELL_CODES = {"S"}


def collect(tickers: list[str] | None = None, lookback_days: int = 30) -> dict:
    """Fetch insider transactions per ticker, aggregate buy/sell $ over lookback_days,
    upsert insider_buy_30d / insider_sell_30d to features_daily.
    """
    tickers = list(tickers) if tickers else universe()["seed_tickers"]
    api_key = env("FINNHUB_API_KEY", required=True)
    today = date.today()
    cutoff = today - timedelta(days=lookback_days)

    inserted = 0
    failed = 0
    with conn() as c, c.cursor() as cur:
        for ticker in tickers:
            try:
                resp = requests.get(BASE_URL, params={"symbol": ticker, "token": api_key}, timeout=10)
                resp.raise_for_status()
                rows = resp.json().get("data", [])

                buy_total = 0.0
                sell_total = 0.0
                for row in rows:
                    txn_date_str = row.get("transactionDate")
                    if not txn_date_str:
                        continue
                    txn_date = date.fromisoformat(txn_date_str)
                    if txn_date < cutoff:
                        continue

                    price = row.get("transactionPrice") or 0
                    change = row.get("change") or 0
                    value = abs(change) * price
                    if value == 0:
                        continue

                    code = row.get("transactionCode")
                    if code in _BUY_CODES:
                        buy_total += value
                    elif code in _SELL_CODES:
                        sell_total += value

                # features_daily.value is NUMERIC(14,6) — large-cap insider trades
                # can run into the hundreds of millions and overflow that. Store in
                # thousands of dollars instead; insider.py only ever computes a
                # buy/sell ratio, which is scale-invariant as long as both sides
                # use the same unit.
                for feature_name, value in (
                    ("insider_buy_30d", buy_total / 1000.0),
                    ("insider_sell_30d", sell_total / 1000.0),
                ):
                    cur.execute(
                        """
                        INSERT INTO features_daily (ticker, date, feature_name, value)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (ticker, date, feature_name) DO UPDATE SET value=EXCLUDED.value
                        """,
                        (ticker, today, feature_name, value),
                    )
                c.commit()
                inserted += 1
            except Exception as e:
                c.rollback()  # clear the aborted-transaction state before the next ticker
                log.warning("finnhub_insider_failed", ticker=ticker, err=str(e))
                failed += 1

    log_activity("finnhub_collector", "collect", "ok", tickers=len(tickers), inserted=inserted, failed=failed)
    return {"tickers": len(tickers), "inserted": inserted, "failed": failed}
