"""Combine per-ticker signals into a single ensemble score."""
from __future__ import annotations

from src.core.db import conn
from src.core.logging import get_logger
from src.strategy.ensemble.regime_weights import apply_regime_overrides
from src.strategy.ensemble.weights import load_weights

log = get_logger("ensemble.combiner")

# Signal names recognized by the ensemble (must match DEFAULT_WEIGHTS keys).
_RECOGNIZED_SIGNALS: list[str] = [
    "sentiment_1d",
    "sentiment_7d",
    "technical_composite",
    "llm_sentiment",
    "regime_overlay",
    "insider_signal",
    "short_interest_signal",
    "options_flow_signal",
    "qlib_alpha",
]

_MIN_SIGNALS = 3


def _fetch_signals(ticker: str, date: str) -> dict[str, float]:
    """Pull signal values from the signals table for (ticker, date).

    Every signal pipeline (sentiment, technical, llm, insider, alpha, ...)
    upserts into `signals`, not `features_daily` — that table is the raw
    feature store (e.g. mom_20d, insider_buy_30d) the signal pipelines read
    *from* to compute these values, not where the computed signals land.
    """
    with conn() as c, c.cursor() as cur:
        cur.execute(
            """
            SELECT signal_name, value
            FROM signals
            WHERE ticker = %s
              AND date = %s
              AND signal_name = ANY(%s)
            """,
            (ticker, date, _RECOGNIZED_SIGNALS),
        )
        rows = cur.fetchall()
    return {row[0]: float(row[1]) for row in rows if row[1] is not None}


def combine_signals(ticker: str, date: str, regime: str) -> float | None:
    """Return the regime-weighted ensemble score for (ticker, date).

    Loads weights ONCE (caller should call load_weights outside hot loops and
    pass pre-loaded weights; this function is self-contained for single calls).

    Returns None if fewer than 3 signals are available in the DB.
    """
    # load_weights() is called once per combine_signals invocation.
    # For batch scoring callers should use combine_signals_batch() or
    # pre-load weights and call _combine_with_weights() directly.
    base_weights = load_weights()
    return _combine_with_weights(ticker, date, regime, base_weights)


def _combine_with_weights(
    ticker: str,
    date: str,
    regime: str,
    base_weights: dict[str, float],
) -> float | None:
    """Internal: combine signals using pre-loaded base weights."""
    try:
        signals = _fetch_signals(ticker, date)
    except Exception:
        log.exception("combine_signals: DB fetch failed for %s %s", ticker, date)
        return None

    if len(signals) < _MIN_SIGNALS:
        log.debug(
            "combine_signals: only %d signals for %s %s (need %d)",
            len(signals),
            ticker,
            date,
            _MIN_SIGNALS,
        )
        return None

    regime_weights = apply_regime_overrides(base_weights, regime)

    weighted_sum = 0.0
    weight_used = 0.0
    for signal_name, weight in regime_weights.items():
        value = signals.get(signal_name)
        if value is not None:
            weighted_sum += value * weight
            weight_used += weight

    if weight_used <= 0:
        return None

    # Normalise by the fraction of weight that was actually used
    score = weighted_sum / weight_used
    log.debug(
        "combine_signals: ticker=%s date=%s regime=%s score=%.4f signals=%d",
        ticker,
        date,
        regime,
        score,
        len(signals),
    )
    return score


def combine_signals_batch(
    tickers: list[str],
    date: str,
    regime: str,
) -> dict[str, float | None]:
    """Batch version: load weights ONCE, score all tickers.

    Returns mapping of ticker -> score (None if <3 signals).
    """
    base_weights = load_weights()  # called once outside the per-ticker loop
    return {
        ticker: _combine_with_weights(ticker, date, regime, base_weights)
        for ticker in tickers
    }
