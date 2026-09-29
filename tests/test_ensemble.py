"""Tests for the ensemble weighting and combining logic."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from src.strategy.ensemble.regime_weights import (
    REGIME_WEIGHT_OVERRIDES,
    apply_regime_overrides,
)
from src.strategy.ensemble.weights import DEFAULT_WEIGHTS


# ─── apply_regime_overrides ────────────────────────────────────────────────


def test_regime_override_renormalises_to_one():
    """Output weights must sum to 1.0 after applying overrides."""
    result = apply_regime_overrides(dict(DEFAULT_WEIGHTS), "Bull/Low-Vol")
    total = sum(result.values())
    assert abs(total - 1.0) < 1e-9


def test_regime_override_bull_low_vol_multipliers():
    """Bull/Low-Vol should amplify sentiment_1d and suppress short_interest_signal."""
    base = {
        "sentiment_1d": 0.15,
        "technical_composite": 0.20,
        "short_interest_signal": 0.10,
    }
    result = apply_regime_overrides(base, "Bull/Low-Vol")

    overrides = REGIME_WEIGHT_OVERRIDES["Bull/Low-Vol"]
    # Verify relative order: sentiment_1d (×1.2) / short_interest_signal (×0.8)
    # should be higher than without overrides
    base_ratio = base["sentiment_1d"] / base["short_interest_signal"]
    result_ratio = result["sentiment_1d"] / result["short_interest_signal"]
    assert result_ratio > base_ratio, "Bull/Low-Vol should favour sentiment_1d over short_interest"


def test_regime_override_bear_high_vol_suppresses_technical():
    """Bear/High-Vol multiplier 0.6 on technical_composite should reduce its relative share.

    With equal base weights, technical (×0.6) ends up lower than short_interest (×1.3).
    """
    # Use equal base weights so multiplier effect is the only driver
    base = {
        "technical_composite": 0.10,
        "insider_signal": 0.10,
        "short_interest_signal": 0.10,
    }
    result = apply_regime_overrides(base, "Bear/High-Vol")

    # technical_composite×0.6 < short_interest_signal×1.3
    assert result["technical_composite"] < result["short_interest_signal"]
    # technical_composite×0.6 < insider_signal×1.1
    assert result["technical_composite"] < result["insider_signal"]


def test_unknown_regime_returns_normalised_base():
    """An unrecognised regime should return renormalised base weights unchanged."""
    base = {"a": 0.3, "b": 0.7}
    result = apply_regime_overrides(base, "Martian/Eclipse")
    assert abs(sum(result.values()) - 1.0) < 1e-9
    # Ratios should be preserved
    assert abs(result["a"] / result["b"] - base["a"] / base["b"]) < 1e-9


def test_sideways_regime_leaves_keys_intact():
    """Sideways regime uses multiplier 1.0 for all listed keys — output should sum to 1."""
    result = apply_regime_overrides(dict(DEFAULT_WEIGHTS), "Sideways")
    assert set(result.keys()) == set(DEFAULT_WEIGHTS.keys())
    assert abs(sum(result.values()) - 1.0) < 1e-9


# ─── combine_signals ───────────────────────────────────────────────────────


def _make_fetchall_side_effect(signal_map: dict[str, float]):
    """Build a mock fetchall return value matching features_daily rows."""
    return [(name, value) for name, value in signal_map.items()]


def test_combine_signals_returns_none_when_fewer_than_3_signals():
    """combine_signals must return None when fewer than 3 signals are in the DB."""
    from src.strategy.ensemble.combiner import combine_signals

    with (
        patch("src.strategy.ensemble.combiner.load_weights", return_value=dict(DEFAULT_WEIGHTS)),
        patch("src.strategy.ensemble.combiner._fetch_signals", return_value={"sentiment_1d": 0.5, "sentiment_7d": 0.3}),
    ):
        result = combine_signals("AAPL", "2025-01-10", "Bull/Low-Vol")
    assert result is None


def test_combine_signals_returns_float_with_enough_signals():
    """combine_signals must return a float when 3+ signals exist."""
    from src.strategy.ensemble.combiner import combine_signals

    signals = {
        "sentiment_1d": 0.8,
        "sentiment_7d": 0.6,
        "technical_composite": 0.7,
        "llm_sentiment": 0.5,
    }
    with (
        patch("src.strategy.ensemble.combiner.load_weights", return_value=dict(DEFAULT_WEIGHTS)),
        patch("src.strategy.ensemble.combiner._fetch_signals", return_value=signals),
    ):
        result = combine_signals("AAPL", "2025-01-10", "Bull/Low-Vol")
    assert result is not None
    assert isinstance(result, float)


def test_combine_signals_db_error_returns_none():
    """combine_signals returns None if the DB fetch raises an exception."""
    from src.strategy.ensemble.combiner import combine_signals

    with (
        patch("src.strategy.ensemble.combiner.load_weights", return_value=dict(DEFAULT_WEIGHTS)),
        patch("src.strategy.ensemble.combiner._fetch_signals", side_effect=RuntimeError("DB down")),
    ):
        result = combine_signals("AAPL", "2025-01-10", "Bull/Low-Vol")
    assert result is None


def test_combine_signals_weighted_sum_is_bounded():
    """Score should be within the range of the input signal values."""
    from src.strategy.ensemble.combiner import combine_signals

    signals = {k: 0.5 for k in DEFAULT_WEIGHTS}  # all signals = 0.5
    with (
        patch("src.strategy.ensemble.combiner.load_weights", return_value=dict(DEFAULT_WEIGHTS)),
        patch("src.strategy.ensemble.combiner._fetch_signals", return_value=signals),
    ):
        result = combine_signals("TSLA", "2025-01-10", "Sideways")
    assert result is not None
    # All signals are 0.5, so weighted sum should also be 0.5
    assert abs(result - 0.5) < 1e-6


# ─── load_weights fallback ─────────────────────────────────────────────────


def test_load_weights_falls_back_to_defaults_on_empty_db():
    """load_weights should return DEFAULT_WEIGHTS when the DB has no rows."""
    from src.strategy.ensemble.weights import load_weights

    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = []
    mock_conn_ctx = MagicMock()
    mock_conn_ctx.__enter__ = MagicMock(return_value=mock_conn_ctx)
    mock_conn_ctx.__exit__ = MagicMock(return_value=False)
    mock_cur_ctx = MagicMock()
    mock_cur_ctx.__enter__ = MagicMock(return_value=mock_cur)
    mock_cur_ctx.__exit__ = MagicMock(return_value=False)
    mock_conn_ctx.cursor = MagicMock(return_value=mock_cur_ctx)

    with patch("src.strategy.ensemble.weights.conn", return_value=mock_conn_ctx):
        result = load_weights()

    assert result == DEFAULT_WEIGHTS


def test_load_weights_falls_back_on_exception():
    """load_weights should return DEFAULT_WEIGHTS if the DB raises an exception."""
    from src.strategy.ensemble.weights import load_weights

    with patch("src.strategy.ensemble.weights.conn", side_effect=RuntimeError("no db")):
        result = load_weights()

    assert result == DEFAULT_WEIGHTS
