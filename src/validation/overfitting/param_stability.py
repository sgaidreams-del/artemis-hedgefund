"""Parameter stability scoring for overfitting detection."""
from __future__ import annotations

import numpy as np

from src.core.logging import get_logger

log = get_logger(__name__)


def stability_score(sharpe_grid: np.ndarray) -> float:
    """Fraction of grid cells within 20% of peak Sharpe.

    A strategy whose performance is robust to parameter choices will have a
    large fraction of the parameter grid near the peak. A highly over-fit
    strategy will have a narrow spike.

    Parameters
    ----------
    sharpe_grid:
        N-dimensional array of Sharpe ratios over a parameter grid.

    Returns
    -------
    Stability score in [0, 1]. 1.0 means all parameter combinations
    perform within 20% of the peak Sharpe.
    """
    grid = np.asarray(sharpe_grid, dtype=float)
    if grid.size == 0:
        raise ValueError("sharpe_grid must not be empty")

    peak = float(np.nanmax(grid))
    if peak <= 0:
        # If best Sharpe is non-positive, use threshold of 20% below 0
        threshold = peak * 0.8  # less negative
        # For flat non-positive grids, all cells are "near" the peak
        near_peak = np.nansum(grid >= threshold)
    else:
        # Within 20% means Sharpe >= peak * 0.80
        threshold = peak * 0.80
        near_peak = np.nansum(grid >= threshold)

    total = np.sum(~np.isnan(grid))
    score = float(near_peak / total) if total > 0 else 0.0

    log.info("param_stability", peak_sharpe=round(peak, 4), score=round(score, 4))
    return score
