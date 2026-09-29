"""Tests for options flow signal classification logic."""
import pytest
from src.data.options_flow import classify_signal


def test_bullish_flow():
    # Unusual volume + heavy calls (low P/C ratio)
    assert classify_signal(iv_rank=40.0, put_call_ratio=0.3, unusual_volume=True) == "bullish_flow"


def test_bearish_flow():
    # Unusual volume + heavy puts (high P/C ratio)
    assert classify_signal(iv_rank=60.0, put_call_ratio=1.8, unusual_volume=True) == "bearish_flow"


def test_neutral_no_unusual_volume():
    # No unusual volume → neutral regardless of P/C ratio
    assert classify_signal(iv_rank=50.0, put_call_ratio=0.3, unusual_volume=False) == "neutral"
    assert classify_signal(iv_rank=50.0, put_call_ratio=1.8, unusual_volume=False) == "neutral"


def test_insufficient_data_no_iv_rank():
    assert classify_signal(iv_rank=None, put_call_ratio=0.8, unusual_volume=False) == "insufficient_data"


def test_insufficient_data_no_pc_ratio():
    assert classify_signal(iv_rank=40.0, put_call_ratio=None, unusual_volume=False) == "insufficient_data"


def test_insufficient_data_both_none():
    assert classify_signal(iv_rank=None, put_call_ratio=None, unusual_volume=True) == "insufficient_data"


def test_neutral_balanced_flow():
    # P/C between 0.5 and 1.5 → neutral even with unusual volume
    assert classify_signal(iv_rank=55.0, put_call_ratio=0.9, unusual_volume=True) == "neutral"


def test_boundary_put_call_exactly_1_5():
    # At the threshold boundary → not unusual enough → neutral
    result = classify_signal(iv_rank=50.0, put_call_ratio=1.5, unusual_volume=True)
    assert result in ("neutral", "bearish_flow")  # boundary is implementation-defined


def test_boundary_put_call_exactly_0_5():
    result = classify_signal(iv_rank=50.0, put_call_ratio=0.5, unusual_volume=True)
    assert result in ("neutral", "bullish_flow")


def test_get_iv_rank_returns_value():
    from unittest.mock import patch, MagicMock
    from contextlib import contextmanager
    from src.data.options_flow import get_iv_rank

    class MockCursor:
        def execute(self, *a, **k): pass
        def fetchone(self): return (62.5,)
        def __enter__(self): return self
        def __exit__(self, *a): pass

    class MockConn:
        def cursor(self): return MockCursor()
        def __enter__(self): return self
        def __exit__(self, *a): pass

    @contextmanager
    def mock_conn():
        yield MockConn()

    with patch("src.data.options_flow.conn", mock_conn):
        assert get_iv_rank("AAPL") == 62.5


def test_get_iv_rank_returns_none_when_no_data():
    from unittest.mock import patch
    from contextlib import contextmanager
    from src.data.options_flow import get_iv_rank

    class MockCursor:
        def execute(self, *a, **k): pass
        def fetchone(self): return None
        def __enter__(self): return self
        def __exit__(self, *a): pass

    class MockConn:
        def cursor(self): return MockCursor()
        def __enter__(self): return self
        def __exit__(self, *a): pass

    @contextmanager
    def mock_conn():
        yield MockConn()

    with patch("src.data.options_flow.conn", mock_conn):
        assert get_iv_rank("ZZZZ") is None
