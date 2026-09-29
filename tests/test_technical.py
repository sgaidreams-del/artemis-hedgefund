import pytest
import numpy as np
import pandas as pd
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# compute_indicators tests
# ---------------------------------------------------------------------------

def test_compute_indicators_no_nan_in_tail():
    """With 100 rows of data, the last row should have no NaN for SMA20 and RSI."""
    from src.signals.technical.indicators import compute_indicators
    np.random.seed(42)
    prices = 100 + np.cumsum(np.random.randn(100) * 0.5)
    df = pd.DataFrame({
        "open": prices * 0.99,
        "high": prices * 1.01,
        "low": prices * 0.98,
        "close": prices,
        "volume": np.random.randint(1_000_000, 5_000_000, 100).astype(float),
    })
    result = compute_indicators(df)
    assert "SMA20" in result.columns
    assert "SMA50" in result.columns
    assert "SMA_cross" in result.columns
    # Last row should have SMA20 (needs 20 rows)
    assert not pd.isna(result.iloc[-1]["SMA20"])


def test_compute_indicators_sma_cross():
    """Verify SMA_cross is +1 when SMA20 > SMA50."""
    from src.signals.technical.indicators import compute_indicators
    # Rising prices → recent SMA20 > SMA50
    prices = np.linspace(50, 150, 100)
    df = pd.DataFrame({
        "open": prices, "high": prices * 1.01,
        "low": prices * 0.99, "close": prices,
        "volume": np.ones(100) * 1e6,
    })
    result = compute_indicators(df)
    assert result.iloc[-1]["SMA_cross"] == 1


def test_compute_indicators_returns_required_columns():
    """compute_indicators adds all expected columns."""
    from src.signals.technical.indicators import compute_indicators
    prices = np.linspace(100, 120, 60)
    df = pd.DataFrame({
        "open": prices * 0.99,
        "high": prices * 1.01,
        "low": prices * 0.98,
        "close": prices,
        "volume": np.ones(60) * 1e6,
    })
    result = compute_indicators(df)
    for col in ["RSI_14", "MACDs_12_26_9", "BBP_5_2.0", "SMA20", "SMA50", "SMA_cross",
                "ATR_14", "OBV"]:
        assert col in result.columns, f"Missing column: {col}"


def test_compute_indicators_sma_cross_negative():
    """Verify SMA_cross is -1 when SMA20 < SMA50 (declining prices)."""
    from src.signals.technical.indicators import compute_indicators
    prices = np.linspace(150, 50, 100)
    df = pd.DataFrame({
        "open": prices, "high": prices * 1.01,
        "low": prices * 0.99, "close": prices,
        "volume": np.ones(100) * 1e6,
    })
    result = compute_indicators(df)
    assert result.iloc[-1]["SMA_cross"] == -1


# ---------------------------------------------------------------------------
# composite score tests
# ---------------------------------------------------------------------------

def _make_db_mock(fetchall_return):
    """Build a mock conn() that supports 'with conn() as c, c.cursor() as cur:' pattern."""
    mock_cur = MagicMock()
    mock_cur.__enter__ = MagicMock(return_value=mock_cur)
    mock_cur.__exit__ = MagicMock(return_value=False)
    mock_cur.fetchall.return_value = fetchall_return

    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = mock_cur
    return mock_conn


def test_composite_in_range():
    """compute_technical_score result is in [-1, +1]."""
    from src.signals.technical.composite import compute_technical_score
    import datetime
    rows = []
    np.random.seed(7)
    prices = 100 + np.cumsum(np.random.randn(60) * 0.5)
    for i, p in enumerate(prices):
        rows.append((datetime.date(2024, 1, 1) + datetime.timedelta(days=i),
                      p * 0.99, p * 1.01, p * 0.98, p, 1_000_000))
    mock_conn = _make_db_mock(rows)
    with patch("src.signals.technical.composite.conn", return_value=mock_conn):
        score = compute_technical_score("AAPL")
    assert score is not None
    assert -1.0 <= score <= 1.0


def test_composite_returns_none_for_insufficient_data():
    from src.signals.technical.composite import compute_technical_score
    mock_conn = _make_db_mock([("2024-01-01", 100, 101, 99, 100, 1e6)] * 5)  # only 5 rows
    with patch("src.signals.technical.composite.conn", return_value=mock_conn):
        result = compute_technical_score("AAPL")
    assert result is None


def test_run_technical_pipeline_returns_count():
    from src.signals.technical.composite import run_technical_pipeline
    with patch("src.signals.technical.composite.compute_technical_score", return_value=0.3):
        mock_conn = _make_db_mock([])
        with patch("src.signals.technical.composite.conn", return_value=mock_conn):
            count = run_technical_pipeline(["AAPL", "MSFT", "GOOGL"])
    assert count == 3


def test_run_technical_pipeline_skips_none_scores():
    """Tickers with None score should not increment the written count."""
    from src.signals.technical.composite import run_technical_pipeline
    scores = [0.3, None, 0.5]
    tickers = ["AAPL", "MSFT", "GOOGL"]
    with patch("src.signals.technical.composite.compute_technical_score", side_effect=scores):
        mock_conn = _make_db_mock([])
        with patch("src.signals.technical.composite.conn", return_value=mock_conn):
            count = run_technical_pipeline(tickers)
    assert count == 2
