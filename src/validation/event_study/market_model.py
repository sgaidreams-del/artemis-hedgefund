"""OLS market model for event study — estimates alpha, beta, residual std."""
from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm

from src.core.logging import get_logger

log = get_logger(__name__)


def fit_market_model(
    stock_returns: pd.Series,
    market_returns: pd.Series,
    estimation_window: int = 120,
) -> dict:
    """OLS regression of stock on market over estimation window.

    Parameters
    ----------
    stock_returns:
        Daily log or simple returns for the stock.
    market_returns:
        Daily returns for the market index (e.g. SPY).
    estimation_window:
        Number of trading days to use for the regression.

    Returns
    -------
    dict with keys: alpha, beta, residual_std, r_squared
    """
    aligned = pd.concat([stock_returns, market_returns], axis=1).dropna()
    aligned.columns = ["stock", "market"]

    if len(aligned) < estimation_window:
        log.warning("market_model.insufficient_data", n=len(aligned), required=estimation_window)
        estimation_window = len(aligned)

    window_data = aligned.iloc[-estimation_window:]
    X = sm.add_constant(window_data["market"].values)
    y = window_data["stock"].values

    model = sm.OLS(y, X).fit()
    alpha = float(model.params[0])
    beta = float(model.params[1])
    residuals = model.resid
    residual_std = float(np.std(residuals, ddof=2))

    log.info("market_model.fit", alpha=round(alpha, 6), beta=round(beta, 4), r2=round(model.rsquared, 4))

    return {
        "alpha": alpha,
        "beta": beta,
        "residual_std": residual_std,
        "r_squared": float(model.rsquared),
    }
