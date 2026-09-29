"""Simple vectorized backtest engine."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.core.logging import get_logger
from src.validation.backtest.metrics import compute_metrics

log = get_logger(__name__)


def run_backtest(
    signals_df: pd.DataFrame,
    prices_df: pd.DataFrame,
    rebalance_freq: str = "D",
) -> dict:
    """Simple vectorized backtest: daily rebalancing using signal as weight proxy.

    Parameters
    ----------
    signals_df:
        DataFrame with same index as prices_df. Each column is a ticker.
        Signal values are treated as portfolio weights (normalized row-wise).
    prices_df:
        DataFrame of adjusted close prices. Same tickers as signals_df.
    rebalance_freq:
        Pandas offset alias for rebalancing frequency (e.g. 'D', 'W', 'M').

    Returns
    -------
    dict with keys: equity_curve (pd.Series), metrics (dict)
    """
    # Align on common dates and tickers
    common_tickers = signals_df.columns.intersection(prices_df.columns)
    if len(common_tickers) == 0:
        raise ValueError("No common tickers between signals_df and prices_df")

    signals = signals_df[common_tickers].copy()
    prices = prices_df[common_tickers].copy()

    # Align index
    common_idx = signals.index.intersection(prices.index)
    signals = signals.loc[common_idx]
    prices = prices.loc[common_idx]

    # Compute daily returns from prices
    daily_returns = prices.pct_change().fillna(0.0)

    # Resample signals to rebalance_freq, then forward-fill for daily application
    if rebalance_freq != "D":
        signals = signals.resample(rebalance_freq).last().reindex(daily_returns.index, method="ffill")

    # Normalize weights row-wise (sum to 1, skip zero rows)
    row_sums = signals.abs().sum(axis=1)
    row_sums = row_sums.replace(0, np.nan)
    weights = signals.div(row_sums, axis=0).fillna(0.0)

    # Portfolio return = sum(weight_i * return_i) for each day
    portfolio_returns = (weights.shift(1) * daily_returns).sum(axis=1)
    portfolio_returns.iloc[0] = 0.0

    equity_curve = (1 + portfolio_returns).cumprod()
    equity_curve.name = "equity"

    metrics = compute_metrics(equity_curve)

    log.info(
        "backtest.complete",
        n_days=len(equity_curve),
        final_value=round(float(equity_curve.iloc[-1]), 4),
        sharpe=round(metrics.get("sharpe", 0.0), 4),
    )

    return {"equity_curve": equity_curve, "metrics": metrics}
