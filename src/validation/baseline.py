"""Baseline benchmark returns for comparison."""
from __future__ import annotations

import pandas as pd

from src.core.logging import get_logger

log = get_logger(__name__)


def buy_and_hold_returns(prices_df: pd.DataFrame, ticker: str = "SPY") -> pd.Series:
    """Simple buy-and-hold daily returns for a benchmark ticker.

    Parameters
    ----------
    prices_df:
        DataFrame of adjusted close prices. Must contain `ticker` as a column.
    ticker:
        Ticker symbol to use as benchmark. Defaults to 'SPY'.

    Returns
    -------
    pd.Series of daily simple returns for the given ticker.
    """
    if ticker not in prices_df.columns:
        available = list(prices_df.columns)
        # Fall back to first available ticker
        if available:
            log.warning("baseline.ticker_not_found", requested=ticker, using=available[0])
            ticker = available[0]
        else:
            raise ValueError(f"Ticker '{ticker}' not found and prices_df has no columns")

    prices = prices_df[ticker].dropna()
    returns = prices.pct_change().dropna()
    returns.name = f"{ticker}_bh_return"

    log.info("baseline.computed", ticker=ticker, n_obs=len(returns))
    return returns
