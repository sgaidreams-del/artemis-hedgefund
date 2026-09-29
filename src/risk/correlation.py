"""Portfolio correlation utilities."""
from __future__ import annotations

from datetime import date, timedelta
from itertools import combinations

import pandas as pd

from src.core.db import conn
from src.core.logging import get_logger

log = get_logger(__name__)


def _fetch_returns(tickers: list[str], lookback_days: int) -> pd.DataFrame:
    """Pull daily OHLCV data for tickers and compute daily close returns.

    Returns a wide DataFrame with date as index and tickers as columns.
    """
    if not tickers:
        return pd.DataFrame()

    cutoff = (date.today() - timedelta(days=lookback_days)).isoformat()
    frames: dict[str, pd.Series] = {}

    with conn() as c, c.cursor() as cur:
        for ticker in tickers:
            cur.execute(
                """
                SELECT date, close
                FROM ohlcv_daily
                WHERE ticker = %s AND date >= %s
                ORDER BY date ASC
                """,
                (ticker, cutoff),
            )
            rows = cur.fetchall()
            if len(rows) < 2:
                log.warning("_fetch_returns: insufficient data", ticker=ticker, rows=len(rows))
                continue
            s = pd.Series({r[0]: float(r[1]) for r in rows}, name=ticker)
            frames[ticker] = s.pct_change().dropna()

    if not frames:
        return pd.DataFrame()

    df = pd.DataFrame(frames)
    df.index = pd.to_datetime(df.index)
    return df


def compute_portfolio_correlation(
    positions: list[str],
    lookback_days: int = 60,
) -> float:
    """Return the average pairwise correlation of daily returns.

    Returns 0.0 if fewer than 2 positions.
    """
    if len(positions) < 2:
        return 0.0

    returns = _fetch_returns(positions, lookback_days)
    valid = [t for t in positions if t in returns.columns]

    if len(valid) < 2:
        return 0.0

    corr_matrix = returns[valid].corr()
    pairs = list(combinations(valid, 2))
    if not pairs:
        return 0.0

    total = sum(corr_matrix.loc[a, b] for a, b in pairs)
    avg = total / len(pairs)
    log.debug("compute_portfolio_correlation", avg_corr=avg, tickers=valid)
    return float(avg)


def crowding_warning(
    positions: list[str],
    threshold: float = 0.80,
) -> list[tuple]:
    """Return (ticker_a, ticker_b, corr) pairs where corr > threshold.

    Shares the _fetch_returns call with compute_portfolio_correlation.
    """
    if len(positions) < 2:
        return []

    returns = _fetch_returns(positions, lookback_days=60)
    valid = [t for t in positions if t in returns.columns]

    if len(valid) < 2:
        return []

    corr_matrix = returns[valid].corr()
    warnings = []
    for a, b in combinations(valid, 2):
        c = float(corr_matrix.loc[a, b])
        if c > threshold:
            warnings.append((a, b, c))
            log.warning("crowding_warning: high correlation", ticker_a=a, ticker_b=b, corr=c)

    return warnings
