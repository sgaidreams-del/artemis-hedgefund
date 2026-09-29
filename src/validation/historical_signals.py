"""Bulk, point-in-time-safe technical_composite signal builder for backtesting.

Reuses the exact same formula/weights as src/signals/technical/composite.py
(compute_technical_score), just computed once per ticker across the whole
history instead of one DB round-trip per (ticker, date) — ~15k round trips
for a 5-year/12-ticker backtest otherwise.

One documented simplification: compute_technical_score's OBV momentum resets
to a fresh 60-row window each call (so the window's first row has no prior
close to determine volume sign, an artifact of the windowed DB query). Here
OBV momentum is computed from the full per-ticker history instead, which
only changes the single boundary row of each 60-day window — immaterial
given the result is clipped to [-1, 1] and OBV is one of five sub-signals at
15% weight. Every other component (RSI, MACD, Bollinger %B, SMA cross) is
purely backward-looking and converges within the indicators' own warm-up, so
computing them on the full series and reading off a row is exactly
equivalent to computing them on a trailing window ending at that row.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.core.db import conn
from src.core.logging import get_logger
from src.signals.technical.composite import (
    WEIGHTS,
    _normalize_bb_pct,
    _normalize_macd_signal,
    _normalize_rsi,
)
from src.signals.technical.indicators import compute_indicators

log = get_logger("historical_signals")

_OBV_WINDOW = 60
_MIN_HISTORY = 20  # mirrors compute_technical_score's len(rows) < 20 -> None


def _obv_window_momentum(close: pd.Series, volume: pd.Series, window: int = _OBV_WINDOW) -> pd.Series:
    """Rolling (last-first)/|first| of a window-cumulated signed-volume series."""
    direction = np.sign(close.diff()).fillna(0.0)
    signed_vol = direction * volume

    def _change(vals: np.ndarray) -> float:
        cum = np.cumsum(vals)
        first, last = cum[0], cum[-1]
        if abs(first) < 1e-9:
            return 0.0
        return float(np.clip((last - first) / (abs(first) + 1e-9), -1.0, 1.0))

    return signed_vol.rolling(window, min_periods=2).apply(_change, raw=True)


def build_historical_technical_signals(
    tickers: list[str], start_date: str, end_date: str
) -> pd.DataFrame:
    """Date-indexed, ticker-columned DataFrame of technical_composite values.

    Pulls extra lookback before start_date (the indicators' own warm-up —
    SMA50 needs 50 prior rows) so values are populated from start_date, not
    biased by an artificial cold start.
    """
    series_by_ticker: dict[str, pd.Series] = {}

    for ticker in tickers:
        with conn() as c, c.cursor() as cur:
            cur.execute(
                """
                SELECT date, open, high, low, close, volume
                FROM ohlcv_daily
                WHERE ticker = %s AND date <= %s
                ORDER BY date ASC
                """,
                (ticker, end_date),
            )
            rows = cur.fetchall()

        if len(rows) < _MIN_HISTORY:
            log.warning("build_historical_technical_signals: insufficient history", ticker=ticker)
            continue

        df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
        df["date"] = pd.to_datetime(df["date"])
        for col in ("open", "high", "low", "close", "volume"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.set_index("date")

        df = compute_indicators(df.reset_index()).set_index(df.index)

        rsi_score = df["RSI_14"].apply(_normalize_rsi)
        macd_score = pd.Series(
            [_normalize_macd_signal(m, p) for m, p in zip(df["MACDs_12_26_9"], df["close"])],
            index=df.index,
        )
        bb_score = df["BBP_5_2.0"].apply(_normalize_bb_pct)
        sma_score = df["SMA_cross"].astype(float)
        obv_score = _obv_window_momentum(df["close"], df["volume"])

        composite = (
            WEIGHTS["rsi"] * rsi_score
            + WEIGHTS["macd"] * macd_score
            + WEIGHTS["bb_pct"] * bb_score
            + WEIGHTS["sma_cross"] * sma_score
            + WEIGHTS["obv"] * obv_score
        ).clip(-1.0, 1.0)

        # First _MIN_HISTORY-1 rows mirror compute_technical_score's "insufficient
        # data" None — mask them rather than report a half-warmed-up score.
        composite.iloc[: _MIN_HISTORY - 1] = np.nan

        series_by_ticker[ticker] = composite

    result = pd.DataFrame(series_by_ticker)
    result = result.loc[(result.index >= pd.Timestamp(start_date)) & (result.index <= pd.Timestamp(end_date))]
    log.info(
        "build_historical_technical_signals: complete",
        tickers=len(series_by_ticker), rows=len(result),
    )
    return result
