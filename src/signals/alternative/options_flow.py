"""Options flow signal — converts stored options_flow rows into a numeric signal.

Replaces the old label-map approach (bullish_flow=0.8, neutral=0.0) with a
continuous score derived directly from put/call ratio, iv_rank, and unusual_volume.

Scoring formula:
  raw   = PCR-based direction, piecewise linear: PCR=0→+1.0, PCR=1→0.0, PCR=2→-1.0
  iv_m  = 0.5 + 0.5*(iv_rank/100)     # amplifies signal when IV is elevated
  vol_m = 1.0 if unusual_volume else 0.5  # downweight ordinary-volume days
  score = clip(raw * iv_m * vol_m, -1, 1)

Example — NVDA July 21 (PCR=0.502, iv_rank=41, unusual=True):
  raw=0.498, iv_m=0.706, vol_m=1.0 → score=+0.35  (was 0.0 with old code)
"""
from __future__ import annotations

from src.core.db import conn
from src.core.logging import get_logger

logger = get_logger(__name__)


def compute_options_flow_signal(ticker: str) -> float | None:
    """Continuous options-flow signal for *ticker* based on most recent DB row.

    Returns None if no data exists. Result is in [-1.0, +1.0].
    """
    with conn() as c, c.cursor() as cur:
        cur.execute(
            """
            SELECT iv_rank, put_call_ratio, unusual_volume
            FROM options_flow
            WHERE ticker = %s
            ORDER BY date DESC
            LIMIT 1
            """,
            (ticker,),
        )
        row = cur.fetchone()

    if row is None:
        return None

    iv_rank_raw, pcr_raw, unusual = row

    if pcr_raw is None:
        return None

    pcr = float(pcr_raw)
    iv_rank = float(iv_rank_raw) if iv_rank_raw is not None else 50.0

    # Piecewise linear PCR → raw direction signal
    # PCR < 1: call-heavy (bullish), mapped [0→+1.0, 1→0.0]
    # PCR > 1: put-heavy (bearish), mapped [1→0.0, 2→-1.0], clamped at -1.0
    if pcr < 1.0:
        raw = min(1.0, 1.0 - pcr)
    else:
        raw = max(-1.0, -(pcr - 1.0))

    # IV rank amplifier: elevated IV = higher-conviction signal
    iv_mult = 0.5 + 0.5 * (iv_rank / 100.0)

    # Volume quality: unusual sweeps carry more information
    vol_mult = 1.0 if unusual else 0.5

    score = raw * iv_mult * vol_mult
    return float(max(-1.0, min(1.0, score)))


def run_options_flow_pipeline(tickers: list[str]) -> int:
    """Compute options-flow signal for each ticker, upsert to signals table."""
    from datetime import date

    today = date.today().isoformat()
    count = 0

    for ticker in tickers:
        try:
            signal_value = compute_options_flow_signal(ticker)
            if signal_value is None:
                logger.info("options_flow_signal: no data", ticker=ticker)
                continue

            with conn() as c, c.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO signals (ticker, date, signal_name, value, confidence)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (ticker, date, signal_name)
                    DO UPDATE SET value=EXCLUDED.value, confidence=EXCLUDED.confidence
                    """,
                    (ticker, today, "options_flow_signal", signal_value, 0.75),
                )
            count += 1
            logger.info("options_flow_signal upserted", ticker=ticker, value=signal_value)
        except Exception:
            logger.exception("options_flow_pipeline failed", ticker=ticker)

    return count
