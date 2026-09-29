"""Signal Registry — weighted ensemble aggregation over all named signals."""
from __future__ import annotations

from datetime import date

from src.core.db import conn
from src.core.logging import get_logger

logger = get_logger(__name__)

SIGNAL_WEIGHTS = {
    "sentiment_1d": 0.15,
    "sentiment_7d": 0.10,
    "technical_composite": 0.20,
    "llm_sentiment": 0.15,
    "regime_overlay": 0.10,
    "insider_signal": 0.10,
    "short_interest_signal": 0.10,
    "options_flow_signal": 0.10,
}


def normalize_signal(raw: float, min_val: float = -1.0, max_val: float = 1.0) -> float:
    """Clamp to [min_val, max_val], then scale to [-1, 1]."""
    clamped = max(min_val, min(max_val, raw))
    if max_val == min_val:
        return 0.0
    # Scale from [min_val, max_val] → [-1, 1]
    return 2.0 * (clamped - min_val) / (max_val - min_val) - 1.0


def get_signals(ticker: str, date_str: str) -> dict[str, float]:
    """Read from signals table WHERE ticker=%s AND date=%s. Returns {signal_name: value}."""
    with conn() as c, c.cursor() as cur:
        cur.execute(
            "SELECT signal_name, value FROM signals WHERE ticker=%s AND date=%s",
            (ticker, date_str),
        )
        rows = cur.fetchall()
    return {row[0]: float(row[1]) for row in rows}


def compute_ensemble_input(ticker: str, date_str: str) -> float | None:
    """Weighted sum of available signals. Returns None if fewer than 3 signals present."""
    signals = get_signals(ticker, date_str)
    available = {name: val for name, val in signals.items() if name in SIGNAL_WEIGHTS}
    if len(available) < 3:
        logger.info(
            "compute_ensemble_input: fewer than 3 signals",
            ticker=ticker,
            date=date_str,
            count=len(available),
        )
        return None
    total_weight = sum(SIGNAL_WEIGHTS[name] for name in available)
    if total_weight == 0.0:
        return None
    weighted_sum = sum(SIGNAL_WEIGHTS[name] * val for name, val in available.items())
    return weighted_sum / total_weight


def get_top_tickers(n: int = 20) -> list[str]:
    """Returns top n tickers by ensemble score for today.

    Fetches all tickers in ONE query, then computes scores locally to avoid
    the N+1 query problem.
    """
    today = date.today().isoformat()
    with conn() as c, c.cursor() as cur:
        cur.execute(
            "SELECT ticker, signal_name, value FROM signals WHERE date=%s",
            (today,),
        )
        rows = cur.fetchall()

    # Group signals by ticker
    ticker_signals: dict[str, dict[str, float]] = {}
    for ticker, signal_name, value in rows:
        if ticker not in ticker_signals:
            ticker_signals[ticker] = {}
        ticker_signals[ticker][signal_name] = float(value)

    # Compute ensemble score for each ticker
    scores: list[tuple[str, float]] = []
    for ticker, signals in ticker_signals.items():
        available = {name: val for name, val in signals.items() if name in SIGNAL_WEIGHTS}
        if len(available) < 3:
            continue
        total_weight = sum(SIGNAL_WEIGHTS[name] for name in available)
        if total_weight == 0.0:
            continue
        score = sum(SIGNAL_WEIGHTS[name] * val for name, val in available.items()) / total_weight
        scores.append((ticker, score))

    scores.sort(key=lambda x: x[1], reverse=True)
    return [ticker for ticker, _ in scores[:n]]
