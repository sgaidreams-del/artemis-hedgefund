"""Short interest signal — bearish signal when short interest is elevated."""
from __future__ import annotations

from src.core.db import conn
from src.core.logging import get_logger

logger = get_logger(__name__)


def compute_short_interest_signal(ticker: str) -> float | None:
    """Read most recent short_interest_pct from features_daily.

    >20% short interest → bearish (-0.5 to -1.0 scaled).
    5-20% → neutral to slight bear.
    <5% → slight bull (0.1).
    Returns None if no data.
    """
    with conn() as c, c.cursor() as cur:
        cur.execute(
            """
            SELECT value
            FROM features_daily
            WHERE ticker = %s
              AND feature_name = 'short_interest_pct'
            ORDER BY date DESC
            LIMIT 1
            """,
            (ticker,),
        )
        row = cur.fetchone()

    if row is None or row[0] is None:
        return None

    pct = float(row[0])

    if pct < 5.0:
        return 0.1
    elif pct <= 20.0:
        # Linear scale from 0.0 (at 5%) to -0.5 (at 20%)
        return -0.5 * (pct - 5.0) / 15.0
    else:
        # > 20%: scale from -0.5 (at 20%) to -1.0 (at 40%+), clamped
        score = -0.5 - 0.5 * (pct - 20.0) / 20.0
        return float(max(-1.0, score))


def run_short_interest_pipeline(tickers: list[str]) -> int:
    """Compute short interest signal for each ticker, upsert to signals table. Return count."""
    from datetime import date

    today = date.today().isoformat()
    count = 0

    for ticker in tickers:
        try:
            signal_value = compute_short_interest_signal(ticker)
            if signal_value is None:
                logger.info("short_interest_signal: no data", ticker=ticker)
                continue

            with conn() as c, c.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO signals (ticker, date, signal_name, value, confidence)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (ticker, date, signal_name)
                    DO UPDATE SET value=EXCLUDED.value, confidence=EXCLUDED.confidence
                    """,
                    (ticker, today, "short_interest_signal", signal_value, 0.65),
                )
            count += 1
            logger.info("short_interest_signal upserted", ticker=ticker, value=signal_value)
        except Exception:
            logger.exception("short_interest_pipeline failed", ticker=ticker)

    return count
