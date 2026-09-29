"""Probability of Backtest Overfitting (PBO) — Bailey et al. 2014."""
from __future__ import annotations

import numpy as np
from scipy import stats

from src.core.logging import get_logger

log = get_logger(__name__)


def prob_backtest_overfitting(
    is_sharpes: list[float],
    oos_sharpes: list[float],
) -> float:
    """Bailey et al. PBO via logit transform.

    For each IS/OOS Sharpe pair from CPCV paths, computes the logit of the
    rank of the OOS Sharpe relative to all OOS Sharpes. PBO is the fraction
    of paths where the best IS strategy does NOT rank well OOS.

    Simplified implementation:
    - For each path, compute the relative rank of the OOS Sharpe.
    - Lambda = logit(rank / n_paths)
    - PBO = P(Lambda <= 0) = fraction of paths where OOS rank <= median.

    Parameters
    ----------
    is_sharpes:
        List of in-sample Sharpe ratios per CPCV path.
    oos_sharpes:
        List of out-of-sample Sharpe ratios per CPCV path (same order).

    Returns
    -------
    PBO as a float in [0, 1]. Values near 1 indicate high overfitting risk.
    """
    if len(is_sharpes) != len(oos_sharpes):
        raise ValueError("is_sharpes and oos_sharpes must have the same length")

    n = len(is_sharpes)
    if n < 2:
        raise ValueError("Need at least 2 paths for PBO")

    is_arr = np.array(is_sharpes, dtype=float)
    oos_arr = np.array(oos_sharpes, dtype=float)

    # Rank of each path's IS Sharpe among all IS Sharpes (1-based)
    is_ranks = stats.rankdata(is_arr)

    # For each path, compute logit of OOS rank (normalized)
    oos_ranks = stats.rankdata(oos_arr)
    oos_rank_norm = oos_ranks / (n + 1)  # avoid 0 and 1

    # Clip to avoid log(0)
    oos_rank_norm = np.clip(oos_rank_norm, 1e-6, 1 - 1e-6)
    lambdas = np.log(oos_rank_norm / (1 - oos_rank_norm))  # logit

    # PBO: fraction of paths where lambda <= 0 (OOS rank <= median)
    # Weight by IS rank so higher-ranked IS paths contribute more
    weights = is_ranks / is_ranks.sum()
    pbo = float(np.sum(weights * (lambdas <= 0)))

    log.info("pbo", n_paths=n, pbo=round(pbo, 4))
    return pbo
