"""Tests for Unit 4 — DeepSeek LLM analyzer (src/signals/llm/deepseek_analyzer.py)."""
from __future__ import annotations

import json
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_conn(row=None):
    """Return a mock conn() context manager.

    row: what cur.fetchone() returns, or None.
    """
    class MockCursor:
        def execute(self, *a, **k): pass
        def fetchone(self): return row
        def __enter__(self): return self
        def __exit__(self, *a): pass

    class MockConn:
        def cursor(self): return MockCursor()
        def commit(self): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass

    @contextmanager
    def mock_conn():
        yield MockConn()

    return mock_conn


def _make_openai_mock(response_dict: dict):
    """Return a mock OpenAI client whose chat.completions.create returns response_dict as JSON."""
    mock_message = MagicMock()
    mock_message.content = json.dumps(response_dict)

    mock_choice = MagicMock()
    mock_choice.message = mock_message

    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_completion

    mock_openai_cls = MagicMock(return_value=mock_client)
    return mock_openai_cls


# ---------------------------------------------------------------------------
# Test 1: analyze_ticker returns expected dict on valid response
# ---------------------------------------------------------------------------

def test_analyze_ticker_returns_expected_dict():
    """analyze_ticker with mocked OpenAI returns the parsed dict."""
    expected = {
        "bull_points": ["Strong revenue growth", "Low P/E"],
        "bear_points": ["Rising rates risk"],
        "sentiment_score": 0.6,
        "confidence": 0.8,
    }
    mock_openai_cls = _make_openai_mock(expected)

    with patch("src.signals.llm.deepseek_analyzer.OpenAI", mock_openai_cls), \
         patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-key"}):
        from src.signals.llm.deepseek_analyzer import analyze_ticker
        result = analyze_ticker(
            ticker="AAPL",
            fundamentals={"pe_ratio": 25.0, "market_cap_b": 2800.0,
                          "dividend_yield": 0.006, "sector": "Technology"},
            recent_headlines=["Apple hits all-time high"],
            technical_score=0.75,
        )

    assert result is not None
    assert result["sentiment_score"] == 0.6
    assert result["confidence"] == 0.8
    assert result["bull_points"] == expected["bull_points"]
    assert result["bear_points"] == expected["bear_points"]


# ---------------------------------------------------------------------------
# Test 2: analyze_ticker returns None on malformed JSON
# ---------------------------------------------------------------------------

def test_analyze_ticker_returns_none_on_malformed_json():
    """analyze_ticker returns None when the LLM returns non-JSON text."""
    mock_message = MagicMock()
    mock_message.content = "Sorry, I cannot analyze that ticker right now."

    mock_choice = MagicMock()
    mock_choice.message = mock_message

    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_completion

    mock_openai_cls = MagicMock(return_value=mock_client)

    with patch("src.signals.llm.deepseek_analyzer.OpenAI", mock_openai_cls), \
         patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-key"}):
        from src.signals.llm.deepseek_analyzer import analyze_ticker
        result = analyze_ticker(
            ticker="MSFT",
            fundamentals={"pe_ratio": 30.0, "market_cap_b": 3000.0,
                          "dividend_yield": 0.008, "sector": "Technology"},
            recent_headlines=[],
            technical_score=0.5,
        )

    assert result is None


# ---------------------------------------------------------------------------
# Test 3: run_llm_pipeline skips all tickers when kill switch is paused
# ---------------------------------------------------------------------------

def test_run_llm_pipeline_skips_all_when_paused():
    """run_llm_pipeline returns 0 without calling analyze_ticker if is_paused() is True."""
    mock_conn = _make_mock_conn(row=(20.0, 1_500_000_000_000, 0.005, "Technology"))

    with patch("src.signals.llm.deepseek_analyzer.is_paused", return_value=True), \
         patch("src.signals.llm.deepseek_analyzer.conn", mock_conn), \
         patch("src.signals.llm.deepseek_analyzer.cfg",
               return_value={"llm": {"max_holdings_analyzed_per_day": 30}}):
        from src.signals.llm.deepseek_analyzer import run_llm_pipeline
        count = run_llm_pipeline(["AAPL", "MSFT", "GOOG"], max_per_day=10)

    assert count == 0


# ---------------------------------------------------------------------------
# Test 4: run_llm_pipeline respects max_per_day limit
# ---------------------------------------------------------------------------

def test_run_llm_pipeline_respects_max_per_day():
    """run_llm_pipeline only processes up to max_per_day tickers."""
    llm_response = {
        "bull_points": ["Good earnings"],
        "bear_points": ["High valuation"],
        "sentiment_score": 0.4,
        "confidence": 0.7,
    }
    mock_openai_cls = _make_openai_mock(llm_response)
    mock_conn = _make_mock_conn(row=(20.0, 1_500_000_000_000, 0.005, "Technology"))

    calls = []

    def fake_analyze(ticker, fundamentals, recent_headlines, technical_score):
        calls.append(ticker)
        return llm_response

    tickers = ["AAPL", "MSFT", "GOOG", "AMZN", "TSLA"]
    max_per_day = 2

    with patch("src.signals.llm.deepseek_analyzer.is_paused", return_value=False), \
         patch("src.signals.llm.deepseek_analyzer.conn", mock_conn), \
         patch("src.signals.llm.deepseek_analyzer.analyze_ticker", side_effect=fake_analyze), \
         patch("src.signals.llm.deepseek_analyzer.time") as mock_time, \
         patch("src.signals.llm.deepseek_analyzer.cfg",
               return_value={"llm": {"max_holdings_analyzed_per_day": 30}}):
        from src.signals.llm.deepseek_analyzer import run_llm_pipeline
        count = run_llm_pipeline(tickers, max_per_day=max_per_day)

    assert count == max_per_day
    assert len(calls) == max_per_day
    assert calls == ["AAPL", "MSFT"]


# ---------------------------------------------------------------------------
# Test 5: analyze_ticker returns None when required keys are missing
# ---------------------------------------------------------------------------

def test_analyze_ticker_returns_none_on_missing_keys():
    """analyze_ticker returns None when the JSON response is missing required keys."""
    incomplete_response = {
        "bull_points": ["Good earnings"],
        # missing: bear_points, sentiment_score, confidence
    }
    mock_openai_cls = _make_openai_mock(incomplete_response)

    with patch("src.signals.llm.deepseek_analyzer.OpenAI", mock_openai_cls), \
         patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-key"}):
        from src.signals.llm.deepseek_analyzer import analyze_ticker
        result = analyze_ticker(
            ticker="NVDA",
            fundamentals={"pe_ratio": 50.0, "market_cap_b": 1000.0,
                          "dividend_yield": 0.001, "sector": "Technology"},
            recent_headlines=[],
            technical_score=0.9,
        )

    assert result is None


# ---------------------------------------------------------------------------
# Test 6: run_llm_pipeline uses cfg default for max_per_day when not specified
# ---------------------------------------------------------------------------

def test_run_llm_pipeline_uses_cfg_default():
    """run_llm_pipeline reads max_holdings_analyzed_per_day from config when max_per_day is None."""
    llm_response = {
        "bull_points": [],
        "bear_points": [],
        "sentiment_score": 0.0,
        "confidence": 0.5,
    }
    calls = []

    def fake_analyze(ticker, fundamentals, recent_headlines, technical_score):
        calls.append(ticker)
        return llm_response

    mock_conn = _make_mock_conn(row=(15.0, 500_000_000_000, 0.02, "Financials"))
    cfg_limit = 3
    tickers = ["A", "B", "C", "D", "E"]

    with patch("src.signals.llm.deepseek_analyzer.is_paused", return_value=False), \
         patch("src.signals.llm.deepseek_analyzer.conn", mock_conn), \
         patch("src.signals.llm.deepseek_analyzer.analyze_ticker", side_effect=fake_analyze), \
         patch("src.signals.llm.deepseek_analyzer.time"), \
         patch("src.signals.llm.deepseek_analyzer.cfg",
               return_value={"llm": {"max_holdings_analyzed_per_day": cfg_limit}}):
        from src.signals.llm.deepseek_analyzer import run_llm_pipeline
        count = run_llm_pipeline(tickers)  # no max_per_day argument

    assert count == cfg_limit
    assert len(calls) == cfg_limit
