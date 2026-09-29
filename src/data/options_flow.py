"""Options flow signal classification.

Classifies options market activity as bullish_flow, bearish_flow, neutral,
or insufficient_data based on IV rank, put/call ratio, and unusual volume flag.
"""
from __future__ import annotations

from typing import Optional

from src.core.db import conn

# Thresholds
_BULLISH_PCR_THRESHOLD = 0.7   # PCR below this = calls > puts by 1.4× = bullish flow
_BEARISH_PCR_THRESHOLD = 1.3   # PCR above this = puts > calls by 1.3× = bearish flow


def classify_signal(
    iv_rank: Optional[float],
    put_call_ratio: Optional[float],
    unusual_volume: bool,
) -> str:
    """Classify options flow activity.

    Parameters
    ----------
    iv_rank:
        Implied-volatility rank (0–100).  None if unavailable.
    put_call_ratio:
        Put volume / call volume ratio.  None if unavailable.
    unusual_volume:
        True when the print is classified as unusually large (block sweep, etc.).

    Returns
    -------
    str
        One of: ``"bullish_flow"``, ``"bearish_flow"``, ``"neutral"``,
        ``"insufficient_data"``.
    """
    if iv_rank is None or put_call_ratio is None:
        return "insufficient_data"

    if not unusual_volume:
        return "neutral"

    if put_call_ratio < _BULLISH_PCR_THRESHOLD:
        return "bullish_flow"
    if put_call_ratio > _BEARISH_PCR_THRESHOLD:
        return "bearish_flow"
    return "neutral"


def get_iv_rank(ticker: str) -> Optional[float]:
    """Most recent IV rank (0-100) for ticker from the options_flow table. None if no data."""
    with conn() as c, c.cursor() as cur:
        cur.execute(
            "SELECT iv_rank FROM options_flow WHERE ticker = %s ORDER BY date DESC LIMIT 1",
            (ticker,),
        )
        row = cur.fetchone()
    if row is None or row[0] is None:
        return None
    return float(row[0])
