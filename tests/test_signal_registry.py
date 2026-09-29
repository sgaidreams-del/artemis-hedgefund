"""Tests for Signal Registry and Alternative Data signals."""
from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_conn_mock(rows):
    """Build a context-manager mock that returns *rows* from cur.fetchall()."""
    cur_mock = MagicMock()
    cur_mock.fetchall.return_value = rows
    cur_mock.fetchone.return_value = rows[0] if rows else None
    cur_mock.__enter__ = lambda s: s
    cur_mock.__exit__ = MagicMock(return_value=False)

    conn_mock = MagicMock()
    conn_mock.cursor.return_value = cur_mock
    conn_mock.__enter__ = lambda s: s
    conn_mock.__exit__ = MagicMock(return_value=False)

    @contextmanager
    def _conn():
        yield conn_mock

    return _conn, cur_mock


def _make_fetchone_conn_mock(row):
    """Build a context-manager mock that returns *row* from cur.fetchone()."""
    cur_mock = MagicMock()
    cur_mock.fetchone.return_value = row
    cur_mock.fetchall.return_value = [row] if row else []
    cur_mock.__enter__ = lambda s: s
    cur_mock.__exit__ = MagicMock(return_value=False)

    conn_mock = MagicMock()
    conn_mock.cursor.return_value = cur_mock
    conn_mock.__enter__ = lambda s: s
    conn_mock.__exit__ = MagicMock(return_value=False)

    @contextmanager
    def _conn():
        yield conn_mock

    return _conn, cur_mock


# ---------------------------------------------------------------------------
# Test 1: get_signals returns correct dict from mocked DB
# ---------------------------------------------------------------------------

def test_get_signals_returns_correct_dict():
    rows = [
        ("sentiment_1d", 0.5),
        ("technical_composite", 0.3),
        ("llm_sentiment", -0.2),
    ]
    mock_conn, _ = _make_conn_mock(rows)

    with patch("src.signals.registry.conn", mock_conn):
        from src.signals.registry import get_signals
        result = get_signals("AAPL", "2026-06-17")

    assert result == {
        "sentiment_1d": 0.5,
        "technical_composite": 0.3,
        "llm_sentiment": -0.2,
    }


# ---------------------------------------------------------------------------
# Test 2: compute_ensemble_input returns None when fewer than 3 signals
# ---------------------------------------------------------------------------

def test_compute_ensemble_input_returns_none_with_fewer_than_3_signals():
    # Only 2 signals in registry SIGNAL_WEIGHTS
    rows = [
        ("sentiment_1d", 0.8),
        ("technical_composite", 0.6),
    ]
    mock_conn, _ = _make_conn_mock(rows)

    with patch("src.signals.registry.conn", mock_conn):
        from src.signals.registry import compute_ensemble_input
        result = compute_ensemble_input("MSFT", "2026-06-17")

    assert result is None


def test_compute_ensemble_input_returns_none_with_zero_signals():
    mock_conn, _ = _make_conn_mock([])

    with patch("src.signals.registry.conn", mock_conn):
        from src.signals.registry import compute_ensemble_input
        result = compute_ensemble_input("TSLA", "2026-06-17")

    assert result is None


# ---------------------------------------------------------------------------
# Test 3: compute_ensemble_input returns weighted sum when 4+ signals available
# ---------------------------------------------------------------------------

def test_compute_ensemble_input_weighted_sum_with_4_signals():
    rows = [
        ("sentiment_1d", 1.0),       # weight 0.15
        ("technical_composite", 1.0), # weight 0.20
        ("llm_sentiment", 1.0),       # weight 0.15
        ("insider_signal", 1.0),      # weight 0.10
    ]
    mock_conn, _ = _make_conn_mock(rows)

    with patch("src.signals.registry.conn", mock_conn):
        from src.signals.registry import compute_ensemble_input
        result = compute_ensemble_input("NVDA", "2026-06-17")

    assert result is not None
    # All signals = 1.0, weighted sum / total_weight = 1.0
    assert abs(result - 1.0) < 1e-9


def test_compute_ensemble_input_correctly_weights_mixed_signals():
    # Manually compute expected result
    # sentiment_1d=1.0 (w=0.15), technical_composite=-1.0 (w=0.20),
    # llm_sentiment=0.5 (w=0.15), regime_overlay=0.0 (w=0.10)
    rows = [
        ("sentiment_1d", 1.0),
        ("technical_composite", -1.0),
        ("llm_sentiment", 0.5),
        ("regime_overlay", 0.0),
    ]
    mock_conn, _ = _make_conn_mock(rows)

    with patch("src.signals.registry.conn", mock_conn):
        from src.signals.registry import compute_ensemble_input
        result = compute_ensemble_input("AMZN", "2026-06-17")

    assert result is not None
    # Expected: (0.15*1.0 + 0.20*(-1.0) + 0.15*0.5 + 0.10*0.0) / (0.15+0.20+0.15+0.10)
    expected = (0.15 * 1.0 + 0.20 * -1.0 + 0.15 * 0.5 + 0.10 * 0.0) / (0.15 + 0.20 + 0.15 + 0.10)
    assert abs(result - expected) < 1e-9


# ---------------------------------------------------------------------------
# Test 4: compute_insider_signal returns positive for net buying
# ---------------------------------------------------------------------------

def test_compute_insider_signal_positive_for_net_buying():
    # buy_30d=100, sell_30d=20 → net=80, total=120 → score=80/120 ≈ 0.667
    rows = [
        ("insider_buy_30d", 100.0),
        ("insider_sell_30d", 20.0),
    ]
    mock_conn, _ = _make_conn_mock(rows)

    with patch("src.signals.alternative.insider.conn", mock_conn):
        from src.signals.alternative.insider import compute_insider_signal
        result = compute_insider_signal("GOOG")

    assert result is not None
    assert result > 0.0
    assert abs(result - (80.0 / 120.0)) < 1e-9


def test_compute_insider_signal_negative_for_net_selling():
    rows = [
        ("insider_buy_30d", 10.0),
        ("insider_sell_30d", 90.0),
    ]
    mock_conn, _ = _make_conn_mock(rows)

    with patch("src.signals.alternative.insider.conn", mock_conn):
        from src.signals.alternative.insider import compute_insider_signal
        result = compute_insider_signal("META")

    assert result is not None
    assert result < 0.0


def test_compute_insider_signal_none_when_no_data():
    mock_conn, _ = _make_conn_mock([])

    with patch("src.signals.alternative.insider.conn", mock_conn):
        from src.signals.alternative.insider import compute_insider_signal
        result = compute_insider_signal("XYZ")

    assert result is None


# ---------------------------------------------------------------------------
# Test 5: compute_options_flow_signal clips result to [-1, 1] when iv_rank > 100
# ---------------------------------------------------------------------------

def test_compute_options_flow_signal_clips_when_iv_rank_over_100():
    # Row is (iv_rank, put_call_ratio, unusual_volume).
    # PCR=0 → raw=+1.0; iv_mult=0.5+0.5*(200/100)=1.5 → 1.5, clipped to 1.0
    mock_conn, cur_mock = _make_fetchone_conn_mock((200.0, 0.0, True))

    with patch("src.signals.alternative.options_flow.conn", mock_conn):
        from src.signals.alternative.options_flow import compute_options_flow_signal
        result = compute_options_flow_signal("AAPL")

    assert result is not None
    assert result == 1.0


def test_compute_options_flow_signal_clips_bearish_when_iv_rank_over_100():
    # PCR=3 → raw clamps at -1.0; × iv_mult 1.5 = -1.5 → clipped to -1.0
    mock_conn, _ = _make_fetchone_conn_mock((200.0, 3.0, True))

    with patch("src.signals.alternative.options_flow.conn", mock_conn):
        from src.signals.alternative.options_flow import compute_options_flow_signal
        result = compute_options_flow_signal("AAPL")

    assert result is not None
    assert result == -1.0


def test_compute_options_flow_signal_normal_case():
    # PCR=0.5 → raw=0.5; iv_rank=50 → iv_mult=0.75; unusual → vol_mult=1.0 → 0.375
    mock_conn, _ = _make_fetchone_conn_mock((50.0, 0.5, True))

    with patch("src.signals.alternative.options_flow.conn", mock_conn):
        from src.signals.alternative.options_flow import compute_options_flow_signal
        result = compute_options_flow_signal("AAPL")

    assert result is not None
    assert abs(result - 0.375) < 1e-9


def test_compute_options_flow_signal_halves_ordinary_volume():
    # Same as normal case but without unusual volume → vol_mult=0.5 → 0.1875
    mock_conn, _ = _make_fetchone_conn_mock((50.0, 0.5, False))

    with patch("src.signals.alternative.options_flow.conn", mock_conn):
        from src.signals.alternative.options_flow import compute_options_flow_signal
        result = compute_options_flow_signal("AAPL")

    assert result is not None
    assert abs(result - 0.1875) < 1e-9


def test_compute_options_flow_signal_none_when_no_data():
    mock_conn, cur_mock = _make_fetchone_conn_mock(None)
    cur_mock.fetchone.return_value = None

    with patch("src.signals.alternative.options_flow.conn", mock_conn):
        from src.signals.alternative.options_flow import compute_options_flow_signal
        result = compute_options_flow_signal("NOOP")

    assert result is None


# ---------------------------------------------------------------------------
# Test: normalize_signal
# ---------------------------------------------------------------------------

def test_normalize_signal_within_range():
    from src.signals.registry import normalize_signal
    assert normalize_signal(0.0) == 0.0
    assert normalize_signal(1.0) == 1.0
    assert normalize_signal(-1.0) == -1.0


def test_normalize_signal_clamps_above_max():
    from src.signals.registry import normalize_signal
    assert normalize_signal(2.0) == 1.0


def test_normalize_signal_clamps_below_min():
    from src.signals.registry import normalize_signal
    assert normalize_signal(-2.0) == -1.0


def test_normalize_signal_custom_range():
    from src.signals.registry import normalize_signal
    # raw=75, min=0, max=100 → scaled to 0.5
    result = normalize_signal(75.0, min_val=0.0, max_val=100.0)
    assert abs(result - 0.5) < 1e-9
