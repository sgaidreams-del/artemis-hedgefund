"""Tests for HMM regime detector (Unit 3)."""
from __future__ import annotations

import pickle
import tempfile
from contextlib import contextmanager
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest
from hmmlearn.hmm import GaussianHMM


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _synthetic_spy_rows(n: int = 600) -> list[tuple]:
    """Generate synthetic (date, close) rows for SPY."""
    rng = np.random.default_rng(42)
    price = 400.0
    rows = []
    start = date(2022, 1, 3)
    for i in range(n):
        price *= 1.0 + rng.normal(0.0003, 0.012)
        price = max(price, 1.0)
        d = start + timedelta(days=i)
        rows.append((d, price))
    return rows


def _synthetic_features_df(n: int = 300) -> pd.DataFrame:
    """Build a synthetic features DataFrame without DB access."""
    rng = np.random.default_rng(0)
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    log_returns = rng.normal(0.0003, 0.012, n)
    vol_20d = pd.Series(log_returns).rolling(20).std().bfill().values
    vol_5d = pd.Series(log_returns).rolling(5).std().bfill().values
    # Avoid division by zero
    vol_ratio = np.where(vol_20d > 0, vol_5d / vol_20d, 1.0)
    return pd.DataFrame(
        {
            "log_return": log_returns,
            "vol_20d": vol_20d,
            "vol_5d": vol_5d,
            "vol_ratio": vol_ratio,
        },
        index=dates,
    )


# ---------------------------------------------------------------------------
# Test 1: build_regime_features with mocked DB
# ---------------------------------------------------------------------------

@contextmanager
def _mock_conn(rows):
    """Context manager that yields a mock connection whose cursor returns rows."""
    mock_cur = MagicMock()
    mock_cur.__enter__ = lambda s: s
    mock_cur.__exit__ = MagicMock(return_value=False)
    mock_cur.fetchall.return_value = rows

    mock_c = MagicMock()
    mock_c.__enter__ = lambda s: s
    mock_c.__exit__ = MagicMock(return_value=False)
    mock_c.cursor.return_value = mock_cur
    yield mock_c


def test_build_regime_features_with_mocked_db():
    """build_regime_features returns a DataFrame with the correct 4 columns."""
    from src.signals.regime.features import build_regime_features

    rows = _synthetic_spy_rows(600)

    @contextmanager
    def fake_conn():
        with _mock_conn(rows) as c:
            yield c

    with patch("src.signals.regime.features.conn", fake_conn):
        df = build_regime_features(n_days=500)

    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ["log_return", "vol_20d", "vol_5d", "vol_ratio"]
    assert len(df) <= 500
    assert df.index.dtype == "datetime64[ns]" or pd.api.types.is_datetime64_any_dtype(df.index)
    # No NaNs should remain after dropna
    assert df.isna().sum().sum() == 0


def test_build_regime_features_returns_correct_column_count():
    """build_regime_features returns exactly 4 feature columns."""
    from src.signals.regime.features import build_regime_features

    rows = _synthetic_spy_rows(600)

    @contextmanager
    def fake_conn():
        with _mock_conn(rows) as c:
            yield c

    with patch("src.signals.regime.features.conn", fake_conn):
        df = build_regime_features(n_days=200)

    assert df.shape[1] == 4


# ---------------------------------------------------------------------------
# Test 2: train_hmm on synthetic 200-row df completes without crash
# ---------------------------------------------------------------------------

def test_train_hmm_completes_without_crash(tmp_path):
    """train_hmm fits a GaussianHMM on synthetic data and saves the model."""
    from src.signals.regime import detector

    features_df = _synthetic_features_df(200)

    # Redirect MODEL_PATH to a temp directory so we don't pollute the repo
    original_path = detector.MODEL_PATH
    try:
        detector.MODEL_PATH = tmp_path / "model.pkl"
        model = detector.train_hmm(features_df, n_components=5)
    finally:
        detector.MODEL_PATH = original_path

    assert isinstance(model, GaussianHMM)
    assert model.n_components == 5
    assert model.means_.shape == (5, 4)


def test_train_hmm_saves_model_to_disk(tmp_path):
    """train_hmm saves a pickle file at MODEL_PATH."""
    from src.signals.regime import detector

    features_df = _synthetic_features_df(200)
    target = tmp_path / "model.pkl"

    original_path = detector.MODEL_PATH
    try:
        detector.MODEL_PATH = target
        detector.train_hmm(features_df, n_components=5)
    finally:
        detector.MODEL_PATH = original_path

    assert target.exists()
    with target.open("rb") as f:
        loaded = pickle.load(f)
    assert isinstance(loaded, GaussianHMM)


# ---------------------------------------------------------------------------
# Test 3: predict_current_regime returns dict with expected keys
# ---------------------------------------------------------------------------

def test_predict_current_regime_returns_expected_keys(tmp_path):
    """predict_current_regime returns a dict with regime_id, label, confidence, transition_probs."""
    from src.signals.regime import detector

    features_df = _synthetic_features_df(200)

    original_path = detector.MODEL_PATH
    try:
        detector.MODEL_PATH = tmp_path / "model.pkl"
        model = detector.train_hmm(features_df, n_components=5)
    finally:
        detector.MODEL_PATH = original_path

    result = detector.predict_current_regime(model, features_df)

    assert isinstance(result, dict)
    assert "regime_id" in result
    assert "label" in result
    assert "confidence" in result
    assert "transition_probs" in result

    assert isinstance(result["regime_id"], int)
    assert isinstance(result["label"], str)
    assert 0.0 <= result["confidence"] <= 1.0
    assert isinstance(result["transition_probs"], list)
    assert len(result["transition_probs"]) == 5


def test_predict_current_regime_label_is_valid(tmp_path):
    """predict_current_regime returns a recognised regime label."""
    from src.signals.regime import detector

    valid_labels = {
        "Bull/Low-Vol",
        "Bull/High-Vol",
        "Bear/Low-Vol",
        "Bear/High-Vol",
        "Sideways",
    }

    features_df = _synthetic_features_df(300)

    original_path = detector.MODEL_PATH
    try:
        detector.MODEL_PATH = tmp_path / "model.pkl"
        model = detector.train_hmm(features_df, n_components=5)
    finally:
        detector.MODEL_PATH = original_path

    result = detector.predict_current_regime(model, features_df)
    assert result["label"] in valid_labels


# ---------------------------------------------------------------------------
# Test 4: label_regime correctly maps states given known means array
# ---------------------------------------------------------------------------

def test_label_regime_no_label_collisions():
    """label_regime assigns distinct labels to all 5 states given a known means array."""
    from src.signals.regime.detector import label_regime

    # Construct means where states are clearly ordered by log_return:
    # state 0: bear/high-vol, state 1: bear/low-vol, state 2: sideways,
    # state 3: bull/low-vol, state 4: bull/high-vol
    # means columns: [log_return, vol_20d, vol_5d, vol_ratio]
    means = np.array([
        [-0.010, 0.020, 0.018, 0.90],  # state 0: bear, high vol
        [-0.005, 0.010, 0.009, 0.90],  # state 1: bear, low vol
        [ 0.000, 0.012, 0.011, 0.92],  # state 2: sideways
        [ 0.005, 0.008, 0.007, 0.88],  # state 3: bull, low vol
        [ 0.010, 0.018, 0.016, 0.89],  # state 4: bull, high vol
    ])

    labels = [label_regime(i, means) for i in range(5)]

    # All 5 labels must be unique — no collisions
    assert len(set(labels)) == 5, f"Label collision detected: {labels}"

    valid = {"Bull/Low-Vol", "Bull/High-Vol", "Bear/Low-Vol", "Bear/High-Vol", "Sideways"}
    assert set(labels) == valid, f"Unexpected labels: {labels}"


def test_label_regime_sideways_is_middle_state():
    """The middle-ranked state by log_return is labelled Sideways."""
    from src.signals.regime.detector import label_regime

    means = np.array([
        [-0.010, 0.015, 0.014, 0.93],  # state 0: worst return
        [-0.005, 0.012, 0.011, 0.92],  # state 1: second worst
        [ 0.001, 0.011, 0.010, 0.91],  # state 2: middle
        [ 0.006, 0.009, 0.008, 0.89],  # state 3: second best
        [ 0.012, 0.020, 0.018, 0.90],  # state 4: best return
    ])

    # After argsort on col 0, middle rank is state 2
    assert label_regime(2, means) == "Sideways"


def test_label_regime_bear_states_at_bottom():
    """States with the lowest log_returns (ranks 0,1) are labelled Bear/..."""
    from src.signals.regime.detector import label_regime

    means = np.array([
        [-0.012, 0.022, 0.020, 0.91],  # state 0: most bearish, high vol
        [-0.006, 0.010, 0.009, 0.90],  # state 1: second most bearish, low vol
        [ 0.001, 0.011, 0.010, 0.91],  # state 2: sideways
        [ 0.007, 0.009, 0.008, 0.89],  # state 3: bull, low vol
        [ 0.013, 0.019, 0.017, 0.89],  # state 4: bull, high vol
    ])

    label_0 = label_regime(0, means)
    label_1 = label_regime(1, means)

    assert label_0.startswith("Bear/"), f"Expected Bear/... got {label_0}"
    assert label_1.startswith("Bear/"), f"Expected Bear/... got {label_1}"
    # They must be different
    assert label_0 != label_1, f"Both bear states got same label: {label_0}"


def test_label_regime_bull_states_at_top():
    """States with the highest log_returns (ranks 3,4) are labelled Bull/..."""
    from src.signals.regime.detector import label_regime

    means = np.array([
        [-0.012, 0.022, 0.020, 0.91],
        [-0.006, 0.010, 0.009, 0.90],
        [ 0.001, 0.011, 0.010, 0.91],
        [ 0.007, 0.009, 0.008, 0.89],  # bull, low vol
        [ 0.013, 0.019, 0.017, 0.89],  # bull, high vol
    ])

    label_3 = label_regime(3, means)
    label_4 = label_regime(4, means)

    assert label_3.startswith("Bull/"), f"Expected Bull/... got {label_3}"
    assert label_4.startswith("Bull/"), f"Expected Bull/... got {label_4}"
    assert label_3 != label_4, f"Both bull states got same label: {label_3}"
