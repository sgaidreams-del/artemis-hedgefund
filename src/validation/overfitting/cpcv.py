"""Combinatorial Purged Cross-Validation (CPCV) for backtest overfitting detection."""
from __future__ import annotations

from itertools import combinations

import numpy as np
import pandas as pd

from src.core.logging import get_logger
from src.validation.backtest.metrics import compute_metrics

log = get_logger(__name__)


def _get_cpcv_splits(n: int, n_splits: int, n_test: int) -> list[tuple[np.ndarray, np.ndarray]]:
    """Generate CPCV train/test index pairs.

    Splits data into n_splits equal groups; for each combination of n_test groups
    as the test set, the remaining groups form the training set.
    """
    group_size = n // n_splits
    groups = [np.arange(i * group_size, min((i + 1) * group_size, n)) for i in range(n_splits)]
    # Last group may be slightly larger
    groups[-1] = np.arange((n_splits - 1) * group_size, n)

    splits: list[tuple[np.ndarray, np.ndarray]] = []
    for test_groups in combinations(range(n_splits), n_test):
        test_idx = np.concatenate([groups[g] for g in test_groups])
        train_idx = np.concatenate([groups[g] for g in range(n_splits) if g not in test_groups])
        splits.append((np.sort(train_idx), np.sort(test_idx)))
    return splits


def run_cpcv(
    signals_df: pd.DataFrame,
    prices_df: pd.DataFrame,
    n_splits: int = 6,
    n_test: int = 2,
) -> dict:
    """Combinatorial purged cross-validation.

    For each CPCV path, computes backtest metrics on the OOS (test) periods and
    compares to the IS (train) Sharpe. Reports the fraction of paths where
    OOS Sharpe > 0 and the average OOS Sharpe.

    Parameters
    ----------
    signals_df, prices_df:
        Strategy signals and prices (same columns / index alignment).
    n_splits:
        Number of equal-length splits of the time series.
    n_test:
        Number of splits used as OOS per CPCV combination.

    Returns
    -------
    dict with keys: win_rate_oos, avg_sharpe_oos, n_paths, paths (list of dicts)
    """
    common_tickers = signals_df.columns.intersection(prices_df.columns)
    signals = signals_df[common_tickers].copy()
    prices = prices_df[common_tickers].copy()
    common_idx = signals.index.intersection(prices.index)
    signals = signals.loc[common_idx]
    prices = prices.loc[common_idx]

    n = len(common_idx)
    if n < n_splits * 10:
        raise ValueError(f"Insufficient data ({n} rows) for {n_splits} splits")

    splits = _get_cpcv_splits(n, n_splits, n_test)
    n_paths = len(splits)

    paths: list[dict] = []
    for i, (train_idx, test_idx) in enumerate(splits):
        try:
            # OOS backtest
            oos_signals = signals.iloc[test_idx]
            oos_prices = prices.iloc[test_idx]

            # Simple vectorized equity curve for OOS
            oos_daily_ret = oos_prices.pct_change().fillna(0.0)
            row_sums = oos_signals.abs().sum(axis=1).replace(0, np.nan)
            oos_weights = oos_signals.div(row_sums, axis=0).fillna(0.0)
            port_ret = (oos_weights.shift(1).fillna(0.0) * oos_daily_ret).sum(axis=1)
            oos_equity = (1 + port_ret).cumprod()

            oos_metrics = compute_metrics(oos_equity)
            oos_sharpe = oos_metrics["sharpe"]

            # IS Sharpe for reference
            is_signals = signals.iloc[train_idx]
            is_prices = prices.iloc[train_idx]
            is_daily_ret = is_prices.pct_change().fillna(0.0)
            is_row_sums = is_signals.abs().sum(axis=1).replace(0, np.nan)
            is_weights = is_signals.div(is_row_sums, axis=0).fillna(0.0)
            is_port_ret = (is_weights.shift(1).fillna(0.0) * is_daily_ret).sum(axis=1)
            is_equity = (1 + is_port_ret).cumprod()
            is_metrics = compute_metrics(is_equity)

            paths.append({
                "path": i,
                "is_sharpe": is_metrics["sharpe"],
                "oos_sharpe": oos_sharpe,
                "oos_win_rate": oos_metrics["win_rate"],
            })
        except Exception as exc:  # noqa: BLE001
            log.warning("cpcv.path_failed", path=i, error=str(exc))
            paths.append({"path": i, "is_sharpe": 0.0, "oos_sharpe": 0.0, "oos_win_rate": 0.0})

    oos_sharpes = [p["oos_sharpe"] for p in paths]
    win_rate_oos = float(np.mean([s > 0 for s in oos_sharpes]))
    avg_sharpe_oos = float(np.mean(oos_sharpes))

    log.info(
        "cpcv.complete",
        n_paths=n_paths,
        win_rate_oos=round(win_rate_oos, 4),
        avg_sharpe_oos=round(avg_sharpe_oos, 4),
    )

    return {
        "win_rate_oos": win_rate_oos,
        "avg_sharpe_oos": avg_sharpe_oos,
        "n_paths": n_paths,
        "paths": paths,
    }
