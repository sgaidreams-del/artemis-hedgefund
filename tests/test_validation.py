"""Tests for src/validation — Unit 12 Validation Pipeline.

Uses 500-row synthetic price / signal data to exercise all major components.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

N = 500
TICKERS = ["AAPL", "MSFT", "SPY"]
RNG = np.random.default_rng(seed=0)


def _make_prices(n: int = N, tickers: list[str] = TICKERS) -> pd.DataFrame:
    """Synthetic log-normal price series."""
    dates = pd.bdate_range("2022-01-03", periods=n)
    log_returns = RNG.normal(0.0003, 0.015, size=(n, len(tickers)))
    prices = np.exp(np.cumsum(log_returns, axis=0)) * 100
    return pd.DataFrame(prices, index=dates, columns=tickers)


def _make_signals(prices: pd.DataFrame) -> pd.DataFrame:
    """Simple momentum signal: sign of 5-day return."""
    ret5 = prices.pct_change(5).fillna(0.0)
    signals = np.sign(ret5)
    return signals


@pytest.fixture(scope="module")
def prices_df() -> pd.DataFrame:
    return _make_prices()


@pytest.fixture(scope="module")
def signals_df(prices_df: pd.DataFrame) -> pd.DataFrame:
    return _make_signals(prices_df)


@pytest.fixture(scope="module")
def equity_curve(signals_df: pd.DataFrame, prices_df: pd.DataFrame) -> pd.Series:
    from src.validation.backtest.engine import run_backtest
    result = run_backtest(signals_df, prices_df)
    return result["equity_curve"]


# ---------------------------------------------------------------------------
# Test 1: compute_metrics returns all expected keys
# ---------------------------------------------------------------------------

def test_compute_metrics_keys(equity_curve: pd.Series) -> None:
    """compute_metrics must return all seven required keys."""
    from src.validation.backtest.metrics import compute_metrics

    metrics = compute_metrics(equity_curve)

    expected_keys = {"sharpe", "sortino", "max_drawdown", "calmar", "win_rate", "profit_factor", "obs_count"}
    assert expected_keys.issubset(metrics.keys()), (
        f"Missing keys: {expected_keys - metrics.keys()}"
    )

    # Sanity bounds
    assert -5.0 <= metrics["max_drawdown"] <= 0.0
    assert 0.0 <= metrics["win_rate"] <= 1.0
    assert metrics["obs_count"] > 0


# ---------------------------------------------------------------------------
# Test 2: run_backtest returns equity curve with correct length
# ---------------------------------------------------------------------------

def test_run_backtest_equity_curve_length(signals_df: pd.DataFrame, prices_df: pd.DataFrame) -> None:
    """Equity curve length must match number of common dates between signals and prices."""
    from src.validation.backtest.engine import run_backtest

    result = run_backtest(signals_df, prices_df)

    assert "equity_curve" in result
    assert "metrics" in result

    common_len = len(signals_df.index.intersection(prices_df.index))
    assert len(result["equity_curve"]) == common_len, (
        f"Expected {common_len} rows, got {len(result['equity_curve'])}"
    )

    # Equity curve should start near 1.0
    assert 0.5 <= float(result["equity_curve"].iloc[0]) <= 2.0


# ---------------------------------------------------------------------------
# Test 3: run_cpcv completes without crash
# ---------------------------------------------------------------------------

def test_run_cpcv_completes(signals_df: pd.DataFrame, prices_df: pd.DataFrame) -> None:
    """CPCV must complete and return expected keys."""
    from src.validation.overfitting.cpcv import run_cpcv

    result = run_cpcv(signals_df, prices_df, n_splits=5, n_test=2)

    assert "win_rate_oos" in result
    assert "avg_sharpe_oos" in result
    assert "n_paths" in result
    assert "paths" in result

    assert 0.0 <= result["win_rate_oos"] <= 1.0
    assert result["n_paths"] > 0
    assert len(result["paths"]) == result["n_paths"]


# ---------------------------------------------------------------------------
# Test 4: deflated_sharpe_ratio returns lower value than raw Sharpe
# ---------------------------------------------------------------------------

def test_deflated_sharpe_less_than_raw() -> None:
    """DSR must return a value <= raw Sharpe probability (i.e. adjusted downward)."""
    from src.validation.overfitting.deflated_sharpe import deflated_sharpe_ratio

    raw_sharpe = 1.5
    n_trials = 100
    n_obs = 252

    dsr = deflated_sharpe_ratio(raw_sharpe, n_trials=n_trials, n_obs=n_obs)

    # DSR is in [0, 1] — it's a probability
    assert 0.0 <= dsr <= 1.0

    # With many trials, DSR should be significantly below 1.0
    assert dsr < 1.0, "DSR should be deflated relative to naive SR=1.5"

    # A raw Sharpe of 1.5 with only 1 trial should give a higher DSR
    dsr_no_inflation = deflated_sharpe_ratio(raw_sharpe, n_trials=1, n_obs=n_obs)
    assert dsr_no_inflation >= dsr, (
        "More trials should lower DSR (more deflation for multiple testing)"
    )


# ---------------------------------------------------------------------------
# Test 5: stability_score returns 1.0 for flat grid
# ---------------------------------------------------------------------------

def test_stability_score_flat_grid() -> None:
    """A flat grid (all equal Sharpes) should yield stability score = 1.0."""
    from src.validation.overfitting.param_stability import stability_score

    flat_grid = np.ones((5, 5)) * 1.2
    score = stability_score(flat_grid)

    assert score == pytest.approx(1.0), f"Expected 1.0 for flat grid, got {score}"


def test_stability_score_spike_grid() -> None:
    """A grid with a single spike should yield a low stability score."""
    from src.validation.overfitting.param_stability import stability_score

    grid = np.zeros((10, 10))
    grid[5, 5] = 2.0  # single spike
    score = stability_score(grid)

    # Only 1 out of 100 cells is within 20% of peak
    assert score < 0.05, f"Expected low score for spike grid, got {score}"


# ---------------------------------------------------------------------------
# Test 6: run_full_validation returns dict with all gate keys
# ---------------------------------------------------------------------------

def test_run_full_validation_gate_keys(signals_df: pd.DataFrame, prices_df: pd.DataFrame) -> None:
    """run_full_validation must return a dict containing all 8 gate keys."""
    from src.validation.scorecard import run_full_validation, GATES

    result = run_full_validation(
        strategy_fn=None,
        signals_df=signals_df,
        prices_df=prices_df,
        n_trials=10,
        benchmark_ticker="SPY",
    )

    assert "passed" in result
    assert "gates" in result
    assert isinstance(result["passed"], bool)

    for gate in GATES:
        assert gate in result["gates"], f"Gate '{gate}' missing from result"
        gate_result = result["gates"][gate]
        assert "passed" in gate_result, f"Gate '{gate}' missing 'passed' key"


# ---------------------------------------------------------------------------
# Bonus tests
# ---------------------------------------------------------------------------

def test_buy_and_hold_returns_length(prices_df: pd.DataFrame) -> None:
    """buy_and_hold_returns should return N-1 values (pct_change drops first NaN)."""
    from src.validation.baseline import buy_and_hold_returns

    returns = buy_and_hold_returns(prices_df, ticker="SPY")
    assert len(returns) == N - 1


def test_t_test_car_significant_car() -> None:
    """A large CAR with small residual std should be flagged as significant."""
    from src.validation.event_study.significance import t_test_car

    result = t_test_car(car=0.10, residual_std=0.01, n_days=20)

    assert "t_stat" in result
    assert "p_value" in result
    assert "significant" in result
    assert result["significant"] is True  # very large t-stat


def test_bootstrap_ci_coverage() -> None:
    """Bootstrap CI lower bound should be less than upper bound."""
    from src.validation.event_study.significance import bootstrap_ci

    data = np.array([0.01, 0.02, -0.01, 0.03, 0.00, 0.02, 0.01, -0.02, 0.04, 0.01])
    lower, upper = bootstrap_ci(data, n_bootstrap=500, alpha=0.05)

    assert lower < upper


def test_walk_forward_windows() -> None:
    """WalkForwardRunner.generate_windows should produce non-overlapping test windows."""
    from src.validation.walk_forward import WalkForwardRunner

    runner = WalkForwardRunner(train_days=100, test_days=50, step_days=50)
    windows = runner.generate_windows(500)

    assert len(windows) > 0
    for (t0_tr, t1_tr), (t0_te, t1_te) in windows:
        # Test window starts where training ends
        assert t1_tr == t0_te
        # No overlap between train and test
        assert t0_te >= t1_tr


def test_spa_test_identical_returns() -> None:
    """SPA test on identical returns should yield p-value near 1.0 (no outperformance)."""
    from src.validation.overfitting.spa_test import spa_test

    returns = RNG.normal(0.001, 0.02, size=252)
    p = spa_test(returns, returns.copy(), n_bootstrap=500)

    # Identical returns → no excess return → p-value should be large
    assert p > 0.5


def test_regime_sharpes_returns_per_regime(equity_curve: pd.Series) -> None:
    """regime_sharpes should return a dict with one entry per unique regime label."""
    from src.validation.overfitting.regime_robustness import regime_sharpes

    n = len(equity_curve)
    labels = pd.Series(
        ["bull"] * (n // 2) + ["bear"] * (n - n // 2),
        index=equity_curve.index,
    )

    result = regime_sharpes(equity_curve, labels)
    assert "bull" in result
    assert "bear" in result
    assert isinstance(result["bull"], float)
    assert isinstance(result["bear"], float)
