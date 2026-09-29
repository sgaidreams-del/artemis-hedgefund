"""Volume anomaly signal.

Flags when today's volume is significantly above its 20-day average —
the single most reliable pre-catalyst marker for event-driven moves
(FDA approvals, earnings surprises, M&A, macro shocks).

Scoring:
  volume_ratio = today_volume / avg_volume_20d
  raw  = log2(volume_ratio)          # 2× normal → +1.0, 4× → +2.0, etc.
  score = clip(raw / 3.0, 0, 1)      # normalise: 8× normal = max signal +1.0

The signal is always ≥ 0: anomalous volume is bullish-directional-neutral —
it means *something is happening*, not *which way*. The ensemble combines it
with directional signals (options_flow, technical_composite) for the full picture.

A volume_ratio < 1.5 returns 0.0 (noise floor).
"""
from __future__ import annotations

import math
from datetime import date

from src.core.db import conn
from src.core.logging import get_logger

logger = get_logger(__name__)

_NOISE_FLOOR_RATIO = 1.5   # ratios below this are ordinary — score = 0
_MAX_RATIO_AT_1 = 8.0      # 8× normal volume → score = 1.0


def compute_volume_anomaly_signal(ticker: str, as_of: date | None = None) -> float | None:
    """Return a volume-anomaly score in [0.0, 1.0], or None if insufficient data.

    Parameters
    ----------
    ticker:
        Equity symbol.
    as_of:
        Upper-bound date for point-in-time use (backtesting).  None = latest.
    """
    with conn() as c, c.cursor() as cur:
        if as_of is not None:
            cur.execute(
                """
                SELECT date, volume
                FROM ohlcv_daily
                WHERE ticker = %s AND date <= %s
                ORDER BY date DESC
                LIMIT 21
                """,
                (ticker, as_of),
            )
        else:
            cur.execute(
                """
                SELECT date, volume
                FROM ohlcv_daily
                WHERE ticker = %s
                ORDER BY date DESC
                LIMIT 21
                """,
                (ticker,),
            )
        rows = cur.fetchall()

    if len(rows) < 6:
        return None

    today_vol = int(rows[0][1])
    prior_vols = [int(r[1]) for r in rows[1:]]  # up to 20 prior days
    avg_vol = sum(prior_vols) / len(prior_vols)

    if avg_vol == 0:
        return None

    ratio = today_vol / avg_vol

    if ratio < _NOISE_FLOOR_RATIO:
        return 0.0

    # log2 scale: 2×→1.0, 4×→2.0, 8×→3.0
    raw = math.log2(ratio)
    score = min(1.0, raw / math.log2(_MAX_RATIO_AT_1))
    return round(score, 6)


def run_volume_anomaly_pipeline(tickers: list[str]) -> int:
    """Compute volume_anomaly_signal for each ticker, upsert to signals table.

    Returns the number of rows written.
    """
    today = date.today().isoformat()
    count = 0

    for ticker in tickers:
        try:
            val = compute_volume_anomaly_signal(ticker)
            if val is None:
                logger.info("volume_anomaly: insufficient data", ticker=ticker)
                continue

            with conn() as c, c.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO signals (ticker, date, signal_name, value, confidence)
                    VALUES (%s, %s, 'volume_anomaly_signal', %s, 0.65)
                    ON CONFLICT (ticker, date, signal_name)
                    DO UPDATE SET value=EXCLUDED.value, confidence=EXCLUDED.confidence
                    """,
                    (ticker, today, val),
                )
            count += 1
            if val > 0:
                logger.info("volume_anomaly upserted", ticker=ticker, value=val)
        except Exception:
            logger.exception("volume_anomaly failed", ticker=ticker)

    return count
