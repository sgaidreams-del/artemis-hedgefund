"""Bailey-López de Prado Deflated Sharpe Ratio."""
from __future__ import annotations

import math

import numpy as np
from scipy import stats

from src.core.logging import get_logger

log = get_logger(__name__)


def deflated_sharpe_ratio(sharpe: float, n_trials: int, n_obs: int) -> float:
    """Bailey-López de Prado Deflated Sharpe Ratio (DSR).

    Adjusts for multiple testing (selection bias) when a strategy is chosen
    from a set of n_trials trials. The DSR is the probability that the true
    Sharpe ratio is positive given the observed Sharpe and the number of trials.

    Under the null hypothesis (no true edge), the maximum expected Sharpe from
    n_trials independent trials is approximately:

        E[max SR] ≈ Z^{-1}(1 - 1/n_trials)

    where Z^{-1} is the inverse standard normal CDF.

    Parameters
    ----------
    sharpe:
        Annualized Sharpe ratio of the selected strategy.
    n_trials:
        Number of strategies/parameter combinations tested.
    n_obs:
        Number of observations (e.g., trading days) used to compute the Sharpe.

    Returns
    -------
    DSR as a float in [0, 1] — probability that true SR > 0 after deflation.
    """
    if n_trials <= 0 or n_obs <= 1:
        raise ValueError("n_trials and n_obs must be positive integers > 1")

    # Expected maximum Sharpe under H0 from n_trials independent draws
    # Using the approximation from Bailey & de Prado (2014)
    gamma = 0.5772156649  # Euler-Mascheroni constant
    max_z = stats.norm.ppf(1 - 1.0 / n_trials) if n_trials > 1 else 0.0

    # Standard error of Sharpe estimator (simplified: 1/sqrt(n_obs))
    sr_std = 1.0 / math.sqrt(n_obs)

    # Deflated t-stat: (SR - E[max SR]) / SE(SR)
    t_deflated = (sharpe - max_z) / sr_std if sr_std > 0 else 0.0

    dsr = float(stats.norm.cdf(t_deflated))

    log.info(
        "deflated_sharpe",
        sharpe=round(sharpe, 4),
        n_trials=n_trials,
        n_obs=n_obs,
        max_expected_sr=round(max_z, 4),
        dsr=round(dsr, 4),
    )

    return dsr
