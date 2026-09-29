import pandas as pd
import numpy as np
from src.core.db import conn
from src.core.logging import get_logger
from src.signals.technical.indicators import compute_indicators

logger = get_logger(__name__)

# Signal weights (sum to 1.0)
WEIGHTS = {
    "rsi": 0.25,        # RSI: overbought/oversold
    "macd": 0.25,       # MACD signal: momentum
    "bb_pct": 0.20,     # Bollinger %B: mean reversion
    "sma_cross": 0.15,  # SMA cross: trend
    "obv": 0.15,        # OBV: volume confirmation
}


def _normalize_rsi(rsi_val: float) -> float:
    """RSI 0-100 → [-1, +1]. 50=neutral, <30=oversold(+1), >70=overbought(-1)"""
    if pd.isna(rsi_val):
        return 0.0
    # Linear: 50→0, 0→+1, 100→-1
    return -(rsi_val - 50) / 50.0


def _normalize_macd_signal(macd_val: float, price: float) -> float:
    """Normalize MACD signal line by price, clamp to [-1, +1]"""
    if pd.isna(macd_val) or price == 0:
        return 0.0
    normalized = macd_val / price * 100  # as % of price
    return float(np.clip(normalized, -1.0, 1.0))


def _normalize_bb_pct(bb_pct: float) -> float:
    """Bollinger %B 0-1 → [-1, +1]. 0=oversold(+1), 1=overbought(-1)"""
    if pd.isna(bb_pct):
        return 0.0
    return -(bb_pct - 0.5) * 2.0


def _normalize_obv_change(obv_series: pd.Series) -> float:
    """Full-series OBV momentum (first→last): positive = bullish, negative = bearish."""
    if len(obv_series) < 2 or obv_series.isna().all():
        return 0.0
    recent = obv_series.dropna()
    if len(recent) < 2:
        return 0.0
    change_pct = (recent.iloc[-1] - recent.iloc[0]) / (abs(recent.iloc[0]) + 1e-9)
    return float(np.clip(change_pct, -1.0, 1.0))


def compute_technical_score(ticker: str, date=None) -> float | None:
    """
    Pull last 60 rows from ohlcv_daily for ticker, run indicators,
    compute weighted composite score in [-1, +1].
    Returns None if insufficient data (<20 rows).

    Args:
        ticker: The equity symbol.
        date: Optional upper-bound date for point-in-time scoring (backtesting).
              If None, uses the most-recent available data.
    """
    with conn() as c, c.cursor() as cur:
        if date is not None:
            cur.execute(
                """
                SELECT date, open, high, low, close, volume
                FROM ohlcv_daily
                WHERE ticker = %s AND date <= %s
                ORDER BY date DESC
                LIMIT 60
                """,
                (ticker, date)
            )
        else:
            cur.execute(
                """
                SELECT date, open, high, low, close, volume
                FROM ohlcv_daily
                WHERE ticker = %s
                ORDER BY date DESC
                LIMIT 60
                """,
                (ticker,)
            )
        rows = cur.fetchall()

    if len(rows) < 20:
        return None

    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
    df = df.sort_values("date").reset_index(drop=True)
    df[["open", "high", "low", "close", "volume"]] = (
        df[["open", "high", "low", "close", "volume"]].astype(float)
    )

    df = compute_indicators(df)

    last = df.iloc[-1]
    price = float(last["close"])

    rsi_score = _normalize_rsi(last.get("RSI_14", float("nan")))
    macd_score = _normalize_macd_signal(last.get("MACDs_12_26_9", float("nan")), price)
    bb_score = _normalize_bb_pct(last.get("BBP_5_2.0", float("nan")))
    sma_score = float(last.get("SMA_cross", 0.0))
    obv_score = _normalize_obv_change(df["OBV"] if "OBV" in df.columns else pd.Series([]))

    composite = (
        WEIGHTS["rsi"] * rsi_score
        + WEIGHTS["macd"] * macd_score
        + WEIGHTS["bb_pct"] * bb_score
        + WEIGHTS["sma_cross"] * sma_score
        + WEIGHTS["obv"] * obv_score
    )
    return float(np.clip(composite, -1.0, 1.0))


def run_technical_pipeline(tickers: list[str]) -> int:
    """Compute technical_composite for each ticker, upsert to signals table."""
    written = 0
    for ticker in tickers:
        try:
            score = compute_technical_score(ticker)
            if score is None:
                continue
            with conn() as c, c.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO signals (ticker, date, signal_name, value, confidence)
                    VALUES (%s, CURRENT_DATE, 'technical_composite', %s, 0.7)
                    ON CONFLICT (ticker, date, signal_name)
                    DO UPDATE SET value = EXCLUDED.value, confidence = EXCLUDED.confidence
                    """,
                    (ticker, score)
                )
            written += 1
        except Exception as e:
            logger.error(f"technical signal failed for {ticker}: {e}")
    logger.info(f"technical_pipeline: wrote {written}/{len(tickers)} signals")
    return written
