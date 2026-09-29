"""Sentiment signal aggregator — queries DB headlines, scores with FinBERT, upserts signals."""
from __future__ import annotations

from src.core.db import conn
from src.core.logging import get_logger
from src.signals.sentiment.finbert import score_headlines

logger = get_logger(__name__)


def compute_sentiment_signal(ticker: str, lookback_hours: int = 24) -> dict | None:
    """Compute a sentiment signal for *ticker* over the last *lookback_hours* hours.

    Returns a signal dict or None when there are no headlines.
    """
    with conn() as c, c.cursor() as cur:
        cur.execute(
            "SELECT headline FROM news_headlines "
            "WHERE %s = ANY(tickers) AND timestamp >= NOW() - INTERVAL '1 hour' * %s",
            (ticker, lookback_hours),
        )
        rows = cur.fetchall()

    if not rows:
        return None

    headlines = [row[0] for row in rows]
    scores = score_headlines(headlines)

    avg_score = sum(scores) / len(scores)
    confidence = min(len(headlines) / 10.0, 1.0)

    signal_name = f"sentiment_{lookback_hours}h"
    return {
        "signal_name": signal_name,
        "value": round(avg_score, 4),
        "confidence": round(confidence, 4),
    }


def run_sentiment_pipeline(tickers: list[str]) -> int:
    """Compute sentiment_1d and sentiment_7d signals for each ticker and upsert to DB.

    Returns the number of signal rows written.
    """
    count = 0
    for ticker in tickers:
        for lookback_hours in (24, 168):
            signal = compute_sentiment_signal(ticker, lookback_hours=lookback_hours)
            if signal is None:
                logger.info(
                    "no_headlines",
                    ticker=ticker,
                    lookback_hours=lookback_hours,
                )
                continue

            with conn() as c, c.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO signals (ticker, date, signal_name, value, confidence)
                    VALUES (%s, CURRENT_DATE, %s, %s, %s)
                    ON CONFLICT (ticker, date, signal_name) DO UPDATE
                    SET value = EXCLUDED.value, confidence = EXCLUDED.confidence
                    """,
                    (ticker, signal["signal_name"], signal["value"], signal["confidence"]),
                )

            logger.info(
                "signal_upserted",
                ticker=ticker,
                signal_name=signal["signal_name"],
                value=signal["value"],
                confidence=signal["confidence"],
            )
            count += 1

    return count
