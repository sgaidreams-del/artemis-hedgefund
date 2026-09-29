"""Tests for trade_memory persistence helpers."""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock, call, patch

import pytest


# ─── Helpers ──────────────────────────────────────────────────────────────


def _make_conn_mock(fetchone_return=None, fetchall_return=None):
    """Build a layered context-manager mock that mimics `with conn() as c, c.cursor() as cur`."""
    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = fetchone_return
    mock_cur.fetchall.return_value = fetchall_return or []

    mock_cur_ctx = MagicMock()
    mock_cur_ctx.__enter__ = MagicMock(return_value=mock_cur)
    mock_cur_ctx.__exit__ = MagicMock(return_value=False)

    mock_c = MagicMock()
    mock_c.cursor.return_value = mock_cur_ctx

    mock_conn_ctx = MagicMock()
    mock_conn_ctx.__enter__ = MagicMock(return_value=mock_c)
    mock_conn_ctx.__exit__ = MagicMock(return_value=False)

    return mock_conn_ctx, mock_c, mock_cur


# ─── log_decision ──────────────────────────────────────────────────────────


def test_log_decision_returns_inserted_id():
    """log_decision should return the id from the RETURNING clause."""
    from src.strategy.memory.trade_memory import log_decision

    mock_conn_ctx, mock_c, mock_cur = _make_conn_mock(fetchone_return=(42,))

    with patch("src.strategy.memory.trade_memory.conn", return_value=mock_conn_ctx):
        result = log_decision(
            ticker="AAPL",
            action="buy",
            entry_price=150.0,
            signals={"sentiment_1d": 0.7},
            debate_summary="Bullish thesis",
            regime="Bull/Low-Vol",
        )

    assert result == 42


def test_log_decision_calls_insert_with_pending_status():
    """log_decision INSERT must set status='pending'."""
    from src.strategy.memory.trade_memory import log_decision

    mock_conn_ctx, mock_c, mock_cur = _make_conn_mock(fetchone_return=(7,))

    with patch("src.strategy.memory.trade_memory.conn", return_value=mock_conn_ctx):
        log_decision(
            ticker="TSLA",
            action="sell",
            entry_price=200.0,
            signals={},
            debate_summary="",
            regime="Bear/High-Vol",
        )

    # The SQL text in the execute call should mention 'pending'
    call_args = mock_cur.execute.call_args
    sql = call_args[0][0]
    assert "pending" in sql


def test_log_decision_commits():
    """log_decision must call c.commit() to persist the row."""
    from src.strategy.memory.trade_memory import log_decision

    mock_conn_ctx, mock_c, mock_cur = _make_conn_mock(fetchone_return=(1,))

    with patch("src.strategy.memory.trade_memory.conn", return_value=mock_conn_ctx):
        log_decision("GOOG", "buy", 100.0, {}, "", "Sideways")

    mock_c.commit.assert_called_once()


# ─── get_memory ────────────────────────────────────────────────────────────


def test_get_memory_returns_list_of_dicts():
    """get_memory should return a list of dicts with the expected keys."""
    from src.strategy.memory.trade_memory import get_memory

    fake_row = (
        1, "AAPL", date(2025, 1, 10), "buy", 150.0,
        '{"s": 0.5}', "summary", "Bull/Low-Vol", "pending",
        None, None, None, None,
    )
    mock_conn_ctx, mock_c, mock_cur = _make_conn_mock(fetchall_return=[fake_row])

    with patch("src.strategy.memory.trade_memory.conn", return_value=mock_conn_ctx):
        result = get_memory("AAPL", n=5)

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["ticker"] == "AAPL"
    assert result[0]["action"] == "buy"


def test_get_memory_respects_n_limit():
    """get_memory should pass n to the LIMIT clause."""
    from src.strategy.memory.trade_memory import get_memory

    mock_conn_ctx, mock_c, mock_cur = _make_conn_mock(fetchall_return=[])

    with patch("src.strategy.memory.trade_memory.conn", return_value=mock_conn_ctx):
        get_memory("NVDA", n=3)

    call_args = mock_cur.execute.call_args
    params = call_args[0][1]
    assert 3 in params  # n=3 must appear in the query parameters


# ─── get_pending_reflections ───────────────────────────────────────────────


def test_get_pending_reflections_filters_by_cutoff():
    """get_pending_reflections should pass the correct cutoff date."""
    from src.strategy.memory.trade_memory import get_pending_reflections

    mock_conn_ctx, mock_c, mock_cur = _make_conn_mock(fetchall_return=[])

    today = date.today()
    expected_cutoff = today - timedelta(days=5)

    with patch("src.strategy.memory.trade_memory.conn", return_value=mock_conn_ctx):
        get_pending_reflections(days_old=5)

    call_args = mock_cur.execute.call_args
    params = call_args[0][1]
    assert expected_cutoff in params


def test_get_pending_reflections_returns_only_pending_rows():
    """The SQL query must include status='pending' filter."""
    from src.strategy.memory.trade_memory import get_pending_reflections

    mock_conn_ctx, mock_c, mock_cur = _make_conn_mock(fetchall_return=[])

    with patch("src.strategy.memory.trade_memory.conn", return_value=mock_conn_ctx):
        get_pending_reflections()

    call_args = mock_cur.execute.call_args
    sql = call_args[0][0]
    assert "pending" in sql


# ─── update_reflection ─────────────────────────────────────────────────────


def test_update_reflection_sets_status_resolved():
    """update_reflection must set status='resolved'."""
    from src.strategy.memory.trade_memory import update_reflection

    mock_conn_ctx, mock_c, mock_cur = _make_conn_mock()

    with patch("src.strategy.memory.trade_memory.conn", return_value=mock_conn_ctx):
        update_reflection(id=5, actual_return=0.03, alpha=0.01, reflection="Good call.")

    call_args = mock_cur.execute.call_args
    sql = call_args[0][0]
    assert "resolved" in sql


def test_update_reflection_commits():
    """update_reflection must call c.commit()."""
    from src.strategy.memory.trade_memory import update_reflection

    mock_conn_ctx, mock_c, mock_cur = _make_conn_mock()

    with patch("src.strategy.memory.trade_memory.conn", return_value=mock_conn_ctx):
        update_reflection(id=5, actual_return=0.03, alpha=0.01, reflection="Good call.")

    mock_c.commit.assert_called_once()
