"""Portfolio weight optimizer using PyPortfolioOpt."""
from __future__ import annotations

import pandas as pd
from pypfopt import EfficientFrontier

from src.core.logging import get_logger

log = get_logger(__name__)


def optimize_weights(
    expected_returns: dict,
    cov_matrix: pd.DataFrame,
    tickers: list[str],
    weight_bounds: tuple = (0.0, 0.25),
) -> dict:
    """Compute optimal portfolio weights using max-Sharpe via PyPortfolioOpt.

    Falls back to equal-weight on any error.
    """
    n = len(tickers)
    if n == 0:
        return {}

    equal_weight = {t: 1.0 / n for t in tickers}

    try:
        er_series = pd.Series({t: expected_returns.get(t, 0.0) for t in tickers})
        cov_sub = cov_matrix.loc[tickers, tickers]

        ef = EfficientFrontier(er_series, cov_sub, weight_bounds=weight_bounds)
        ef.max_sharpe()
        weights = ef.clean_weights()
        log.info("optimize_weights: max_sharpe succeeded", tickers=tickers)
        return dict(weights)
    except Exception as exc:
        log.warning("optimize_weights: falling back to equal-weight", error=str(exc))
        return equal_weight


def compute_expected_returns(signals: dict[str, float]) -> dict[str, float]:
    """Convert a signal in [-1, 1] to a proxy annual expected return.

    Uses signal * 0.10 as the annual return estimate.
    """
    return {ticker: signal * 0.10 for ticker, signal in signals.items()}
