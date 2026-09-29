"""Event-driven portfolio simulator with transaction costs."""
from __future__ import annotations

import pandas as pd
import numpy as np

from src.core.logging import get_logger
from src.validation.backtest.metrics import compute_metrics

log = get_logger(__name__)


def simulate(
    signals_df: pd.DataFrame,
    prices_df: pd.DataFrame,
    transaction_cost_bps: float = 5.0,
) -> dict:
    """Event-driven simulation: fills at close + (cost_bps / 10000).

    On each day where signals change, a 'trade' is recorded at the closing
    price adjusted by transaction cost. Portfolio value evolves based on
    position P&L each day.

    Parameters
    ----------
    signals_df:
        DataFrame of signal values (position direction/size), same shape as prices_df.
    prices_df:
        DataFrame of close prices.
    transaction_cost_bps:
        One-way transaction cost in basis points. Applied to the notional of
        each trade as a drag on the equity curve.

    Returns
    -------
    dict with keys: equity_curve (pd.Series), trades (list[dict]),
                    metrics (dict)
    """
    cost_rate = transaction_cost_bps / 10_000.0

    common_tickers = signals_df.columns.intersection(prices_df.columns)
    signals = signals_df[common_tickers].copy()
    prices = prices_df[common_tickers].copy()

    common_idx = signals.index.intersection(prices.index)
    signals = signals.loc[common_idx]
    prices = prices.loc[common_idx]

    # Normalize weights
    row_sums = signals.abs().sum(axis=1).replace(0, np.nan)
    weights = signals.div(row_sums, axis=0).fillna(0.0)

    daily_returns = prices.pct_change().fillna(0.0)

    # Detect rebalances (where weights change)
    weight_changes = weights.diff().abs().sum(axis=1)
    weight_changes.iloc[0] = weights.abs().sum(axis=1).iloc[0]  # initial allocation

    trades: list[dict] = []
    portfolio_value = 1.0
    equity_values: list[float] = [portfolio_value]
    prev_weights = pd.Series(0.0, index=common_tickers)

    for i, date in enumerate(common_idx):
        if i == 0:
            continue

        current_weights = weights.loc[date]

        # Apply daily return from previous day's weights
        day_ret = (prev_weights * daily_returns.loc[date]).sum()
        portfolio_value *= 1 + day_ret

        # Apply transaction costs if rebalancing today
        if weight_changes.loc[date] > 1e-8:
            turnover = (current_weights - prev_weights).abs().sum() / 2.0
            cost = portfolio_value * turnover * cost_rate
            portfolio_value -= cost

            for ticker in common_tickers:
                old_w = float(prev_weights[ticker])
                new_w = float(current_weights[ticker])
                if abs(new_w - old_w) > 1e-8:
                    fill_price = float(prices.loc[date, ticker]) * (1 + cost_rate * np.sign(new_w - old_w))
                    trades.append({
                        "date": date,
                        "ticker": ticker,
                        "old_weight": old_w,
                        "new_weight": new_w,
                        "fill_price": fill_price,
                        "portfolio_value": portfolio_value,
                    })
            prev_weights = current_weights.copy()

        equity_values.append(portfolio_value)

    equity_curve = pd.Series(equity_values, index=common_idx, name="equity")
    metrics = compute_metrics(equity_curve)

    log.info(
        "simulator.complete",
        n_trades=len(trades),
        final_value=round(float(equity_curve.iloc[-1]), 4),
        sharpe=round(metrics.get("sharpe", 0.0), 4),
    )

    return {"equity_curve": equity_curve, "trades": trades, "metrics": metrics}
