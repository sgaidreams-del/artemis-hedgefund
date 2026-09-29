"""Deliberately trip each Phase 3 loss/drawdown halt — mirrors test_pretrade.py's style."""
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from src.risk.limits import (
    check_consecutive_loss_halt,
    check_daily_loss_halt,
    check_trailing_drawdown_halt,
)


def _mock_conn(fetchone_value=None, fetchall_value=None):
    class MockCursor:
        def execute(self, *a, **k): pass
        def fetchone(self): return fetchone_value
        def fetchall(self): return fetchall_value or []
        def __enter__(self): return self
        def __exit__(self, *a): pass

    class MockConn:
        def cursor(self): return MockCursor()
        def __enter__(self): return self
        def __exit__(self, *a): pass

    @contextmanager
    def mock_conn():
        yield MockConn()
    return mock_conn


def test_daily_loss_halt_trips_on_breach():
    # yesterday closed at 100k, today equity dropped 5% (> 3% threshold)
    with patch("src.risk.limits.conn", _mock_conn(fetchone_value=(100_000.0,))):
        assert check_daily_loss_halt(95_000.0) is True


def test_daily_loss_halt_passes_within_threshold():
    with patch("src.risk.limits.conn", _mock_conn(fetchone_value=(100_000.0,))):
        assert check_daily_loss_halt(99_000.0) is False


def test_daily_loss_halt_no_history_does_not_trip():
    with patch("src.risk.limits.conn", _mock_conn(fetchone_value=None)):
        assert check_daily_loss_halt(50_000.0) is False


def test_trailing_drawdown_halt_trips_on_breach():
    # peak was 200k, now at 150k = -25% drawdown, past -15% threshold
    with patch("src.risk.limits.conn", _mock_conn(fetchone_value=(200_000.0,))):
        assert check_trailing_drawdown_halt(150_000.0) is True


def test_trailing_drawdown_halt_passes_within_threshold():
    with patch("src.risk.limits.conn", _mock_conn(fetchone_value=(200_000.0,))):
        assert check_trailing_drawdown_halt(190_000.0) is False


def test_trailing_drawdown_halt_new_peak_does_not_trip():
    # current equity itself is the new all-time high
    with patch("src.risk.limits.conn", _mock_conn(fetchone_value=(100_000.0,))):
        assert check_trailing_drawdown_halt(120_000.0) is False


def test_consecutive_loss_halt_trips_after_n_losing_days():
    rows = [(-0.01,), (-0.02,), (-0.005,)]  # 3 consecutive losses, threshold=3
    with patch("src.risk.limits.conn", _mock_conn(fetchall_value=rows)):
        assert check_consecutive_loss_halt() is True


def test_consecutive_loss_halt_one_winning_day_resets():
    rows = [(-0.01,), (0.02,), (-0.005,)]  # middle day was a win
    with patch("src.risk.limits.conn", _mock_conn(fetchall_value=rows)):
        assert check_consecutive_loss_halt() is False


def test_consecutive_loss_halt_not_enough_history():
    rows = [(-0.01,), (-0.02,)]  # only 2 days, threshold needs 3
    with patch("src.risk.limits.conn", _mock_conn(fetchall_value=rows)):
        assert check_consecutive_loss_halt() is False
