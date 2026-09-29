"""Tests for the FinBERT sentiment signal pipeline."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from src.signals.sentiment.finbert import score_headlines
from src.signals.sentiment.aggregator import compute_sentiment_signal, run_sentiment_pipeline


# ---------------------------------------------------------------------------
# finbert.score_headlines tests
# ---------------------------------------------------------------------------


def test_score_headlines_positive():
    """Positive label with 0.9 confidence → +0.9."""
    mock_pipe = MagicMock(return_value=[{"label": "positive", "score": 0.9}])
    with patch("src.signals.sentiment.finbert._pipe", mock_pipe):
        result = score_headlines(["good news"])
    assert result == pytest.approx([0.9])


def test_score_headlines_empty():
    """Empty input returns empty list without calling the model."""
    result = score_headlines([])
    assert result == []


def test_score_headlines_mixed():
    """Mixed labels produce the correct sign direction."""
    mock_pipe = MagicMock(
        return_value=[
            {"label": "positive", "score": 0.8},
            {"label": "negative", "score": 0.7},
            {"label": "neutral", "score": 0.6},
        ]
    )
    with patch("src.signals.sentiment.finbert._pipe", mock_pipe):
        result = score_headlines(["great earnings", "terrible loss", "no change"])

    assert result[0] > 0, "positive headline should have positive score"
    assert result[1] < 0, "negative headline should have negative score"
    assert result[2] == pytest.approx(0.0), "neutral headline should have zero score"


# ---------------------------------------------------------------------------
# aggregator.compute_sentiment_signal tests
# ---------------------------------------------------------------------------


def _make_mock_conn(rows):
    """Return a callable mock that simulates conn() as a context manager.

    Matches the real codebase pattern:
        with conn() as c, c.cursor() as cur:
            cur.execute(...)
            rows = cur.fetchall()
    """
    mock_cursor = MagicMock()
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_cursor.fetchall.return_value = rows

    mock_conn_ctx = MagicMock()
    mock_conn_ctx.__enter__ = MagicMock(return_value=mock_conn_ctx)
    mock_conn_ctx.__exit__ = MagicMock(return_value=False)
    # c.cursor() returns the mock_cursor context manager
    mock_conn_ctx.cursor.return_value = mock_cursor

    def mock_conn_factory():
        return mock_conn_ctx

    return mock_conn_factory


def test_compute_sentiment_signal_no_headlines():
    """When the DB returns no rows, returns None."""
    mock_conn = _make_mock_conn([])
    with patch("src.signals.sentiment.aggregator.conn", mock_conn):
        result = compute_sentiment_signal("AAPL")
    assert result is None


def test_compute_sentiment_signal_with_headlines():
    """5 headlines with uniform score 0.5 → value=0.5, confidence=0.5."""
    rows = [("headline",)] * 5
    mock_conn = _make_mock_conn(rows)
    with patch("src.signals.sentiment.aggregator.conn", mock_conn), \
         patch("src.signals.sentiment.aggregator.score_headlines", return_value=[0.5] * 5):
        result = compute_sentiment_signal("AAPL", lookback_hours=24)

    assert result is not None
    assert result["value"] == pytest.approx(0.5)
    assert result["confidence"] == pytest.approx(0.5)
    assert result["signal_name"] == "sentiment_24h"


# ---------------------------------------------------------------------------
# aggregator.run_sentiment_pipeline tests
# ---------------------------------------------------------------------------


def test_run_sentiment_pipeline_upsert():
    """For each ticker, upsert is called for sentiment_1d and sentiment_7d signals."""
    fake_signal_1d = {"signal_name": "sentiment_24h", "value": 0.3, "confidence": 0.4}
    fake_signal_7d = {"signal_name": "sentiment_168h", "value": 0.2, "confidence": 0.6}

    # Build a mock that matches: with conn() as c, c.cursor() as cur: cur.execute(...)
    mock_cursor = MagicMock()
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)

    mock_conn_ctx = MagicMock()
    mock_conn_ctx.__enter__ = MagicMock(return_value=mock_conn_ctx)
    mock_conn_ctx.__exit__ = MagicMock(return_value=False)
    mock_conn_ctx.cursor.return_value = mock_cursor

    def mock_conn_factory():
        return mock_conn_ctx

    def _fake_signal(ticker, lookback_hours=24):
        if lookback_hours == 24:
            return fake_signal_1d
        return fake_signal_7d

    with patch("src.signals.sentiment.aggregator.conn", mock_conn_factory), \
         patch("src.signals.sentiment.aggregator.compute_sentiment_signal", side_effect=_fake_signal):
        count = run_sentiment_pipeline(["AAPL", "TSLA"])

    # 2 tickers × 2 lookback windows = 4 upserts
    assert count == 4
    # cur.execute was called once per upsert
    assert mock_cursor.execute.call_count == 4

    # Verify INSERT … ON CONFLICT was used in every call
    for call_args in mock_cursor.execute.call_args_list:
        sql = call_args[0][0]
        assert "ON CONFLICT" in sql
        assert "INSERT INTO signals" in sql
