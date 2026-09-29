"""Performance metrics for an equity curve."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.core.logging import get_logger

log = get_logger(__name__)

ANNUALIZATION = 252  # trading days per year


def compute_metrics(equity_curve: pd.Series) -> dict:
    """Compute standard portfolio performance metrics.

    Parameters
    ----------
    equity_curve:
        Cumulative product series (starts near 1.0, e.g. from (1+r).cumprod()).

    Returns
    -------
    dict with keys: sharpe, sortino, max_drawdown, calmar, win_rate,
                    profit_factor, obs_count
    """
    ec = equity_curve.dropna()
    if len(ec) < 2:
        return {
            "sharpe": 0.0,
            "sortino": 0.0,
            "max_drawdown": 0.0,
            "calmar": 0.0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "obs_count": len(ec),
        }

    # Daily returns from equity curve
    daily_ret = ec.pct_change().dropna()
    n = len(daily_ret)

    mean_ret = daily_ret.mean()
    std_ret = daily_ret.std(ddof=1)

    # Sharpe (annualized, risk-free = 0)
    sharpe = (mean_ret / std_ret * np.sqrt(ANNUALIZATION)) if std_ret > 0 else 0.0

    # Sortino (downside deviation)
    downside = daily_ret[daily_ret < 0]
    downside_std = downside.std(ddof=1) if len(downside) > 1 else 0.0
    sortino = (mean_ret / downside_std * np.sqrt(ANNUALIZATION)) if downside_std > 0 else 0.0

    # Max drawdown
    roll_max = ec.cummax()
    drawdown = (ec - roll_max) / roll_max
    max_drawdown = float(drawdown.min())  # negative value

    # Calmar ratio: annualized return / abs(max_drawdown)
    total_return = float(ec.iloc[-1] / ec.iloc[0] - 1)
    years = n / ANNUALIZATION
    ann_return = (1 + total_return) ** (1 / max(years, 1e-6)) - 1
    calmar = ann_return / abs(max_drawdown) if max_drawdown != 0 else 0.0

    # Win rate
    win_rate = float((daily_ret > 0).sum() / n) if n > 0 else 0.0

    # Profit factor: sum of gains / sum of losses
    gains = daily_ret[daily_ret > 0].sum()
    losses = abs(daily_ret[daily_ret < 0].sum())
    profit_factor = float(gains / losses) if losses > 0 else float(gains > 0)

    metrics = {
        "sharpe": float(sharpe),
        "sortino": float(sortino),
        "max_drawdown": float(max_drawdown),
        "calmar": float(calmar),
        "win_rate": float(win_rate),
        "profit_factor": float(profit_factor),
        "obs_count": n,
    }

    log.debug("metrics.computed", **{k: round(v, 4) if isinstance(v, float) else v for k, v in metrics.items()})
    return metrics
