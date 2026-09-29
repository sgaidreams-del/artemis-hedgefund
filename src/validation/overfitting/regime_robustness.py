"""Regime robustness: per-regime Sharpe ratio computation."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.core.logging import get_logger
from src.validation.backtest.metrics import compute_metrics

log = get_logger(__name__)

ANNUALIZATION = 252


def regime_sharpes(
    equity_curve: pd.Series,
    regime_labels: pd.Series,
) -> dict[str, float]:
    """Compute Sharpe ratio separately per regime.

    Parameters
    ----------
    equity_curve:
        Cumulative equity curve (indexed by date).
    regime_labels:
        Series of regime labels (e.g. 'bull', 'bear', 'sideways') with the
        same or overlapping index as equity_curve.

    Returns
    -------
    dict mapping regime name to annualized Sharpe ratio.
    An empty dict is returned if no matching dates exist for a regime.
    """
    common_idx = equity_curve.index.intersection(regime_labels.index)
    if len(common_idx) == 0:
        log.warning("regime_sharpes.no_common_index")
        return {}

    eq = equity_curve.loc[common_idx]
    labels = regime_labels.loc[common_idx]
    daily_ret = eq.pct_change().dropna()
    labels_aligned = labels.loc[daily_ret.index]

    unique_regimes = labels_aligned.unique()
    result: dict[str, float] = {}

    for regime in unique_regimes:
        mask = labels_aligned == regime
        ret_slice = daily_ret[mask]
        if len(ret_slice) < 5:
            result[str(regime)] = 0.0
            continue

        mean_ret = ret_slice.mean()
        std_ret = ret_slice.std(ddof=1)
        sharpe = (mean_ret / std_ret * np.sqrt(ANNUALIZATION)) if std_ret > 0 else 0.0
        result[str(regime)] = float(sharpe)

    log.info("regime_sharpes", regimes=list(result.keys()), sharpes={k: round(v, 4) for k, v in result.items()})
    return result
