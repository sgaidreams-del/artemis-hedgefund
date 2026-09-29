"""Unit tests for the QLib alpha model pipeline (Unit 7)."""
from __future__ import annotations

import pickle
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest


# ── Helper: build synthetic feature DataFrame ────────────────────────────────

def _make_feature_df(n_tickers: int = 5, n_days: int = 20) -> pd.DataFrame:
    """Build a synthetic multi-index (ticker, date) feature DataFrame."""
    rng = np.random.default_rng(42)
    tickers = [f"T{i:02d}" for i in range(n_tickers)]
    dates = pd.date_range("2024-01-01", periods=n_days, freq="B")
    idx = pd.MultiIndex.from_product([tickers, dates], names=["ticker", "date"])
    cols = [
        "mom_5d", "mom_20d", "mom_60d",
        "vol_20d", "vol_60d",
        "rev_5d",
        "turnover_20d",
        "pe_ratio_norm",
        "market_cap_log",
    ]
    data = rng.standard_normal((len(idx), len(cols)))
    return pd.DataFrame(data, index=idx, columns=cols)


# ── Test 1: build_alpha_features returns expected shape with mocked DB ────────

def test_build_alpha_features_shape():
    """build_alpha_features with mocked DB returns expected multi-index DataFrame."""
    from src.strategy.alpha.features import build_alpha_features

    n_tickers = 3
    n_days = 30
    tickers = ["AAPL", "MSFT", "GOOG"]
    dates = pd.date_range("2024-01-01", periods=n_days, freq="B")

    # Build synthetic OHLCV rows
    rng = np.random.default_rng(7)
    ohlcv_rows = []
    for tkr in tickers:
        price = 100.0
        for dt in dates:
            price *= 1 + rng.normal(0, 0.01)
            ohlcv_rows.append((tkr, dt.date(), price * 0.99, price * 1.01, price * 0.98, price, int(1e6)))

    # Build description tuples: each element is a tuple where [0] is the col name
    def make_description(col_names):
        return [(name,) for name in col_names]

    def make_conn_context(rows, col_names):
        """Return a context manager that yields a connection whose cursor() yields a cursor."""
        cur = MagicMock()
        cur.fetchall.return_value = rows
        cur.description = make_description(col_names)
        cur.__enter__ = lambda s: s
        cur.__exit__ = MagicMock(return_value=False)

        mock_c = MagicMock()
        mock_c.cursor.return_value = cur
        mock_c.__enter__ = lambda s: s
        mock_c.__exit__ = MagicMock(return_value=False)

        ctx = MagicMock()
        ctx.__enter__ = lambda s: mock_c
        ctx.__exit__ = MagicMock(return_value=False)
        return ctx

    ohlcv_ctx = make_conn_context(
        ohlcv_rows,
        ["ticker", "date", "open", "high", "low", "close", "volume"],
    )
    feat_ctx = make_conn_context([], ["ticker", "date", "pe_ratio", "market_cap"])

    call_count = [0]

    def conn_side_effect():
        call_count[0] += 1
        return ohlcv_ctx if call_count[0] == 1 else feat_ctx

    with patch("src.strategy.alpha.features.conn", side_effect=conn_side_effect):
        df = build_alpha_features(tickers, "2024-01-01", "2024-03-01")

    # Should have multi-index with ticker and date levels
    assert isinstance(df, pd.DataFrame)
    assert df.index.names == ["ticker", "date"]

    expected_cols = {
        "mom_5d", "mom_20d", "mom_60d",
        "vol_20d", "vol_60d",
        "rev_5d",
        "turnover_20d",
        "pe_ratio_norm",
        "market_cap_log",
    }
    assert set(df.columns) == expected_cols, f"Unexpected columns: {set(df.columns)}"

    # Should have entries for each ticker
    tickers_in_df = df.index.get_level_values("ticker").unique().tolist()
    assert set(tickers_in_df) == set(tickers)


# ── Test 2: train_model on synthetic 100-row feature df completes ─────────────

def test_train_model_synthetic():
    """train_model on synthetic 100-row feature df completes without crash."""
    import sys
    import types
    import lightgbm as lgb
    from src.strategy.alpha import training

    # Build a 100-row synthetic feature df that training.py can consume
    rng = np.random.default_rng(99)
    tickers = [f"S{i:02d}" for i in range(10)]
    dates = pd.date_range("2023-01-01", periods=10, freq="B")
    idx = pd.MultiIndex.from_product([tickers, dates], names=["ticker", "date"])
    feature_cols = training.FEATURE_COLS
    data = rng.standard_normal((len(idx), len(feature_cols)))
    df = pd.DataFrame(data, index=idx, columns=feature_cols)

    # Stub out src.data.universe so the local import inside train_model doesn't fail
    fake_universe_mod = types.ModuleType("src.data.universe")
    fake_universe_mod.get_universe = lambda: tickers

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_model_path = Path(tmpdir) / "qlib" / "model.pkl"

        with patch.object(training, "MODEL_PATH", tmp_model_path), \
             patch("src.strategy.alpha.features.build_alpha_features", return_value=df), \
             patch.dict(sys.modules, {"src.data.universe": fake_universe_mod}):

            booster = training.train_model(lookback_days=30)

    assert booster is not None
    assert isinstance(booster, lgb.Booster)


# ── Test 3: predict_alpha with mocked model returns dict of correct shape ─────

def test_predict_alpha_shape():
    """predict_alpha with a mocked model returns a dict with one score per ticker."""
    from src.strategy.alpha import qlib_model

    tickers = ["AAPL", "MSFT", "TSLA", "AMZN"]
    as_of_date = "2024-06-01"

    # Build a synthetic feature df for those tickers / that date
    feature_cols = qlib_model.FEATURE_COLS
    rng = np.random.default_rng(5)
    dates = pd.date_range("2024-04-01", periods=45, freq="B")
    idx = pd.MultiIndex.from_product([tickers, dates], names=["ticker", "date"])
    data = rng.standard_normal((len(idx), len(feature_cols)))
    feat_df = pd.DataFrame(data, index=idx, columns=feature_cols)

    mock_booster = MagicMock()
    mock_booster.predict.return_value = rng.standard_normal(len(tickers))

    with patch.object(qlib_model, "load_model", return_value=mock_booster), \
         patch("src.strategy.alpha.features.build_alpha_features", return_value=feat_df):

        scores = qlib_model.predict_alpha(tickers, as_of_date)

    assert isinstance(scores, dict)
    assert len(scores) == len(tickers)
    for tkr in tickers:
        assert tkr in scores
        assert -1.0 <= scores[tkr] <= 1.0, f"Score {scores[tkr]} out of [-1, 1] for {tkr}"


# ── Test 4: _model_reset deletes the model file ───────────────────────────────

def test_model_reset_deletes_file():
    """_model_reset deletes MODEL_PATH when the file exists."""
    from src.strategy.alpha import qlib_model

    with tempfile.TemporaryDirectory() as tmpdir:
        fake_model_path = Path(tmpdir) / "qlib" / "model.pkl"
        fake_model_path.parent.mkdir(parents=True, exist_ok=True)
        fake_model_path.write_bytes(b"fake model data")

        assert fake_model_path.exists()

        with patch.object(qlib_model, "MODEL_PATH", fake_model_path):
            qlib_model._model_reset()

        assert not fake_model_path.exists()


def test_model_reset_noop_when_missing():
    """_model_reset does not raise when MODEL_PATH does not exist."""
    from src.strategy.alpha import qlib_model

    with tempfile.TemporaryDirectory() as tmpdir:
        missing_path = Path(tmpdir) / "qlib" / "no_model.pkl"
        assert not missing_path.exists()

        with patch.object(qlib_model, "MODEL_PATH", missing_path):
            qlib_model._model_reset()  # should not raise
