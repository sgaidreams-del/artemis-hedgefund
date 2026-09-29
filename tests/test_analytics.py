"""Unit tests for dashboard_api.analytics calculation utilities."""
import math
import pytest
from dashboard_api.analytics import (
    sharpe_ratio,
    sortino_ratio,
    max_drawdown,
    running_drawdown,
    win_rate,
    profit_factor,
    correlation_matrix,
)


# ── sharpe_ratio ─────────────────────────────────────────────────────────────

def test_sharpe_positive_returns():
    import random; random.seed(1)
    returns = [0.001 + random.gauss(0, 0.005) for _ in range(252)]
    sr = sharpe_ratio(returns)
    assert sr is not None
    assert sr > 0

def test_sharpe_returns_none_under_30_obs():
    assert sharpe_ratio([0.001] * 29) is None

def test_sharpe_returns_none_zero_std():
    # All identical → std == 0
    assert sharpe_ratio([0.0] * 100) is None

def test_sharpe_negative_returns():
    import random; random.seed(2)
    returns = [-0.001 + random.gauss(0, 0.003) for _ in range(252)]
    sr = sharpe_ratio(returns)
    assert sr is not None
    assert sr < 0

def test_sharpe_annualized():
    # known: daily return 0.001, std ≈ 0 but tiny noise forces finite std
    import random; random.seed(42)
    returns = [0.001 + random.gauss(0, 0.0001) for _ in range(252)]
    sr = sharpe_ratio(returns)
    assert sr is not None
    assert sr > 10  # very high sharpe due to low noise


# ── sortino_ratio ────────────────────────────────────────────────────────────

def test_sortino_no_negative_returns():
    returns = [0.001] * 100
    assert sortino_ratio(returns) is None  # zero downside std

def test_sortino_mixed_returns():
    returns = [0.005, -0.002, 0.003, -0.001] * 30
    s = sortino_ratio(returns)
    assert s is not None
    assert isinstance(s, float)

def test_sortino_greater_than_sharpe_with_asymmetric_returns():
    # positively skewed returns → sortino > sharpe
    returns = [0.002] * 80 + [-0.001] * 20
    sr = sharpe_ratio(returns)
    sor = sortino_ratio(returns)
    if sr is not None and sor is not None:
        assert sor > sr


# ── max_drawdown ─────────────────────────────────────────────────────────────

def test_max_drawdown_flat():
    assert max_drawdown([100.0] * 50) == 0.0

def test_max_drawdown_monotonic_up():
    curve = [100 + i for i in range(50)]
    assert max_drawdown(curve) == 0.0

def test_max_drawdown_single_drop():
    curve = [100, 110, 90, 95, 105]
    dd = max_drawdown(curve)
    assert dd < 0
    # peak=110, trough=90 → drawdown = (90-110)/110 ≈ -0.1818
    assert abs(dd - (90 - 110) / 110) < 0.001

def test_max_drawdown_empty():
    assert max_drawdown([]) == 0.0

def test_max_drawdown_negative():
    curve = [100, 80, 60, 70, 90]
    dd = max_drawdown(curve)
    assert dd <= -0.40  # peak 100 → trough 60 = -40%


# ── running_drawdown ─────────────────────────────────────────────────────────

def test_running_drawdown_length():
    curve = [100, 105, 95, 110, 100]
    rd = running_drawdown(curve)
    assert len(rd) == len(curve)

def test_running_drawdown_first_point_zero():
    curve = [100, 95, 105]
    rd = running_drawdown(curve)
    assert rd[0] == 0.0

def test_running_drawdown_all_nonpositive():
    curve = [100, 90, 95, 85, 100]
    rd = running_drawdown(curve)
    assert all(v <= 0 for v in rd)


# ── win_rate ─────────────────────────────────────────────────────────────────

def test_win_rate_empty():
    assert win_rate([]) is None

def test_win_rate_all_wins():
    assert win_rate([1, 2, 3]) == pytest.approx(1.0)

def test_win_rate_all_losses():
    assert win_rate([-1, -2, -3]) == pytest.approx(0.0)

def test_win_rate_mixed():
    assert win_rate([1, -1, 1, -1]) == pytest.approx(0.5)


# ── profit_factor ─────────────────────────────────────────────────────────────

def test_profit_factor_no_losses():
    assert profit_factor([1, 2, 3]) is None

def test_profit_factor_all_losses():
    pf = profit_factor([-1, -2])
    assert pf == pytest.approx(0.0)

def test_profit_factor_balanced():
    # wins = 10, losses = -10 → factor = 1.0
    pf = profit_factor([10, -10])
    assert pf == pytest.approx(1.0)

def test_profit_factor_good():
    pf = profit_factor([15, -5, 10, -3])
    assert pf is not None
    assert pf > 1.5  # 25 / 8 ≈ 3.1


# ── correlation_matrix ───────────────────────────────────────────────────────

def test_correlation_matrix_empty():
    result = correlation_matrix({})
    assert result["tickers"] == []
    assert result["matrix"] == []

def test_correlation_matrix_single_ticker():
    result = correlation_matrix({"AAPL": [0.001, 0.002, -0.001]})
    assert result["tickers"] == []
    assert result["matrix"] == []

def test_correlation_matrix_two_tickers_identical():
    r = [0.001, -0.002, 0.003, -0.001, 0.002] * 10
    result = correlation_matrix({"A": r, "B": r})
    assert len(result["tickers"]) == 2
    assert len(result["matrix"]) == 2
    # diagonal = 1.0
    assert abs(result["matrix"][0][0] - 1.0) < 1e-9
    # identical series → corr = 1.0
    assert abs(result["matrix"][0][1] - 1.0) < 1e-6

def test_correlation_matrix_uncorrelated():
    import random; random.seed(99)
    a = [random.gauss(0, 1) for _ in range(100)]
    b = [random.gauss(0, 1) for _ in range(100)]
    result = correlation_matrix({"A": a, "B": b})
    assert result["matrix"][0][1] == pytest.approx(result["matrix"][1][0], abs=1e-9)
