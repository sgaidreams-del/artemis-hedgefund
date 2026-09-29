"""Insider trading signal — net buy/sell flow from features_daily."""
from __future__ import annotations

from src.core.db import conn
from src.core.logging import get_logger

logger = get_logger(__name__)


def compute_insider_signal(ticker: str) -> float | None:
    """Read features_daily WHERE ticker=%s AND feature_name IN ('insider_buy_30d','insider_sell_30d')
    AND date >= NOW()-7 days. ORDER BY date DESC.

    Returns positive score for net buying, negative for net selling, None if no data.
    Uses explicit key assignment from the first matching row for each feature_name
    (not dict comprehension, which could overwrite newer with older rows).
    """
    with conn() as c, c.cursor() as cur:
        cur.execute(
            """
            SELECT feature_name, value
            FROM features_daily
            WHERE ticker = %s
              AND feature_name IN ('insider_buy_30d', 'insider_sell_30d')
              AND date >= NOW() - INTERVAL '7 days'
            ORDER BY date DESC
            """,
            (ticker,),
        )
        rows = cur.fetchall()

    if not rows:
        return None

    # Use explicit assignment — first row per feature_name is the most recent
    features: dict[str, float] = {}
    for feature_name, value in rows:
        if feature_name not in features:
            features[feature_name] = float(value)

    buy = features.get("insider_buy_30d")
    sell = features.get("insider_sell_30d")

    if buy is None and sell is None:
        return None

    net_buy = (buy or 0.0) - (sell or 0.0)
    total = (buy or 0.0) + (sell or 0.0)

    if total == 0.0:
        return 0.0

    # Normalize net buy to [-1, 1] using total activity as denominator
    score = net_buy / total
    return float(max(-1.0, min(1.0, score)))


def run_insider_pipeline(tickers: list[str]) -> int:
    """Compute insider signal for each ticker, upsert to signals table. Return count."""
    from datetime import date

    today = date.today().isoformat()
    count = 0

    for ticker in tickers:
        try:
            signal_value = compute_insider_signal(ticker)
            if signal_value is None:
                logger.info("insider_signal: no data", ticker=ticker)
                continue

            with conn() as c, c.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO signals (ticker, date, signal_name, value, confidence)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (ticker, date, signal_name)
                    DO UPDATE SET value=EXCLUDED.value, confidence=EXCLUDED.confidence
                    """,
                    (ticker, today, "insider_signal", signal_value, 0.7),
                )
            count += 1
            logger.info("insider_signal upserted", ticker=ticker, value=signal_value)
        except Exception:
            logger.exception("insider_pipeline failed", ticker=ticker)

    return count
