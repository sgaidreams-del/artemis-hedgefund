"""Statistical significance tests for event study CAR."""
from __future__ import annotations

import numpy as np
from scipy import stats

from src.core.logging import get_logger

log = get_logger(__name__)


def t_test_car(car: float, residual_std: float, n_days: int) -> dict:
    """t-test for CAR significance.

    Test statistic: CAR / (residual_std * sqrt(n_days))
    Under H0: CAR = 0, this follows approximately t(n_days - 1).

    Returns
    -------
    dict with keys: t_stat, p_value, significant (bool at 5%)
    """
    if residual_std <= 0 or n_days <= 0:
        raise ValueError("residual_std and n_days must be positive")

    se = residual_std * np.sqrt(n_days)
    t_stat = car / se if se > 0 else 0.0
    p_value = float(2 * stats.t.sf(abs(t_stat), df=n_days - 1))
    significant = p_value < 0.05

    log.info("t_test_car", t_stat=round(t_stat, 4), p_value=round(p_value, 4), significant=significant)

    return {
        "t_stat": float(t_stat),
        "p_value": p_value,
        "significant": significant,
    }


def bootstrap_ci(
    car_series: np.ndarray,
    n_bootstrap: int = 1000,
    alpha: float = 0.05,
) -> tuple[float, float]:
    """Bootstrap confidence interval for the mean of car_series.

    Resamples with replacement to estimate the sampling distribution of the mean.

    Returns
    -------
    (lower, upper) confidence interval at (1 - alpha) level.
    """
    car_series = np.asarray(car_series, dtype=float)
    rng = np.random.default_rng(seed=42)
    boot_means = np.array(
        [rng.choice(car_series, size=len(car_series), replace=True).mean() for _ in range(n_bootstrap)]
    )
    lower = float(np.percentile(boot_means, 100 * alpha / 2))
    upper = float(np.percentile(boot_means, 100 * (1 - alpha / 2)))

    log.info("bootstrap_ci", lower=round(lower, 6), upper=round(upper, 6), alpha=alpha)
    return lower, upper
