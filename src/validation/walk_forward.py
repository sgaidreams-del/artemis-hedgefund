"""Walk-forward analysis runner."""
from __future__ import annotations

from typing import Callable

import pandas as pd

from src.core.logging import get_logger
from src.validation.backtest.engine import run_backtest
from src.validation.backtest.metrics import compute_metrics

log = get_logger(__name__)


class WalkForwardRunner:
    """Walk-forward validation: repeatedly trains on a window and tests on the next.

    Parameters
    ----------
    train_days:
        Number of trading days in each training window.
    test_days:
        Number of trading days in each test (OOS) window.
    step_days:
        Number of days to step forward between windows (controls overlap).
    """

    def __init__(
        self,
        train_days: int = 252,
        test_days: int = 63,
        step_days: int = 21,
    ) -> None:
        self.train_days = train_days
        self.test_days = test_days
        self.step_days = step_days

    def generate_windows(self, n_total_days: int) -> list[tuple[tuple[int, int], tuple[int, int]]]:
        """Generate (train_range, test_range) index tuples for a series of length n_total_days.

        Returns
        -------
        List of ((train_start, train_end), (test_start, test_end)) index tuples.
        Each range is half-open: [start, end).
        """
        windows: list[tuple[tuple[int, int], tuple[int, int]]] = []
        start = 0
        while True:
            train_end = start + self.train_days
            test_end = train_end + self.test_days
            if test_end > n_total_days:
                break
            windows.append(((start, train_end), (train_end, test_end)))
            start += self.step_days

        log.info("walk_forward.windows", n_windows=len(windows), n_total_days=n_total_days)
        return windows

    def run(
        self,
        strategy_fn: Callable[[pd.DataFrame, pd.DataFrame], pd.DataFrame],
        signals_df: pd.DataFrame,
        prices_df: pd.DataFrame,
    ) -> list[dict]:
        """Run walk-forward validation.

        Parameters
        ----------
        strategy_fn:
            Callable that takes (train_signals, train_prices) and returns a
            DataFrame of signals for the test period. Alternatively, if the
            strategy does not need re-fitting, it can simply return the provided
            signals_df slice. Signature: fn(signals, prices) -> signals.
        signals_df:
            Full signals DataFrame.
        prices_df:
            Full prices DataFrame.

        Returns
        -------
        List of dicts, one per walk-forward window:
        {window_idx, train_range, test_range, is_sharpe, oos_sharpe, oos_metrics}
        """
        common_tickers = signals_df.columns.intersection(prices_df.columns)
        signals = signals_df[common_tickers].copy()
        prices = prices_df[common_tickers].copy()
        common_idx = signals.index.intersection(prices.index)
        signals = signals.loc[common_idx]
        prices = prices.loc[common_idx]

        n = len(common_idx)
        windows = self.generate_windows(n)

        results: list[dict] = []
        for i, (train_range, test_range) in enumerate(windows):
            t0_train, t1_train = train_range
            t0_test, t1_test = test_range

            train_signals = signals.iloc[t0_train:t1_train]
            train_prices = prices.iloc[t0_train:t1_train]
            test_signals = signals.iloc[t0_test:t1_test]
            test_prices = prices.iloc[t0_test:t1_test]

            try:
                # Allow strategy_fn to re-fit on train data and return test signals
                fitted_test_signals = strategy_fn(train_signals, train_prices)
                if fitted_test_signals is None or len(fitted_test_signals) == 0:
                    fitted_test_signals = test_signals

                # Align fitted signals with test prices
                common_test_idx = fitted_test_signals.index.intersection(test_prices.index)
                if len(common_test_idx) == 0:
                    fitted_test_signals = test_signals

                is_result = run_backtest(train_signals, train_prices)
                oos_result = run_backtest(fitted_test_signals, test_prices)

                results.append({
                    "window_idx": i,
                    "train_range": train_range,
                    "test_range": test_range,
                    "is_sharpe": is_result["metrics"]["sharpe"],
                    "oos_sharpe": oos_result["metrics"]["sharpe"],
                    "oos_metrics": oos_result["metrics"],
                    "oos_equity_curve": oos_result["equity_curve"],
                })
            except Exception as exc:  # noqa: BLE001
                log.warning("walk_forward.window_failed", window=i, error=str(exc))
                results.append({
                    "window_idx": i,
                    "train_range": train_range,
                    "test_range": test_range,
                    "is_sharpe": 0.0,
                    "oos_sharpe": 0.0,
                    "oos_metrics": {},
                    "error": str(exc),
                })

        log.info("walk_forward.complete", n_windows=len(results))
        return results
