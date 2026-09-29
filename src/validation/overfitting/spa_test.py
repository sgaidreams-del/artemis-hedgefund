"""Hansen's Superior Predictive Ability (SPA) test — simplified bootstrap implementation."""
from __future__ import annotations

import numpy as np

from src.core.logging import get_logger

log = get_logger(__name__)


def spa_test(
    strategy_returns: np.ndarray,
    benchmark_returns: np.ndarray,
    n_bootstrap: int = 1000,
) -> float:
    """Hansen's SPA test (simplified bootstrap version).

    Tests H0: the strategy does NOT outperform the benchmark on average.

    The test statistic is the mean excess return (strategy - benchmark).
    The bootstrap distribution is obtained by resampling the excess returns
    under the null (centered at 0).

    Parameters
    ----------
    strategy_returns:
        Daily returns of the strategy.
    benchmark_returns:
        Daily returns of the benchmark. Must be same length as strategy_returns.
    n_bootstrap:
        Number of bootstrap replications.

    Returns
    -------
    p-value for H0: strategy is not better than benchmark (two-tailed on mean excess return).
    Small p-value (< 0.05) means strategy significantly outperforms benchmark.
    """
    strat = np.asarray(strategy_returns, dtype=float)
    bench = np.asarray(benchmark_returns, dtype=float)

    if len(strat) != len(bench):
        raise ValueError("strategy_returns and benchmark_returns must have the same length")

    excess = strat - bench
    n = len(excess)

    # Observed test statistic: mean excess return
    t_obs = float(np.mean(excess))

    # Bootstrap under H0 (center the excess returns)
    rng = np.random.default_rng(seed=42)
    centered = excess - np.mean(excess)  # null: mean = 0
    boot_stats = np.array(
        [rng.choice(centered, size=n, replace=True).mean() for _ in range(n_bootstrap)]
    )

    # p-value: fraction of bootstrap samples with |t_boot| >= |t_obs|
    p_value = float(np.mean(np.abs(boot_stats) >= abs(t_obs)))

    log.info("spa_test", t_obs=round(t_obs, 6), p_value=round(p_value, 4), n=n)
    return p_value
