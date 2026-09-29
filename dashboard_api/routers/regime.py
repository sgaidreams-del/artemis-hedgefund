"""Market-regime endpoint — SPEC §11.1 Regime / Macro overlay."""
from __future__ import annotations

import logging
import math

import yfinance as yf
from fastapi import APIRouter

from src.core.db import conn

router = APIRouter(prefix="/api/regime", tags=["regime"])
log = logging.getLogger(__name__)


def _classify(ma50: float, ma200: float) -> str:
    if ma50 > ma200 * 1.005:
        return "bull"
    if ma50 < ma200 * 0.995:
        return "bear"
    return "sideways"


def _realized_vol(closes: list[float], window: int = 20) -> float | None:
    if len(closes) < window + 1:
        return None
    recent = closes[-(window + 1):]
    returns = [
        (recent[i] - recent[i - 1]) / recent[i - 1]
        for i in range(1, len(recent))
        if recent[i - 1] != 0
    ]
    if len(returns) < 2:
        return None
    mu = sum(returns) / len(returns)
    variance = sum((r - mu) ** 2 for r in returns) / (len(returns) - 1)
    return math.sqrt(variance) * math.sqrt(252)


@router.get("/current")
def current():
    try:
        # Prefer HMM output from Phase 2
        with conn() as c, c.cursor() as cur:
            cur.execute(
                "SELECT regime, confidence, ma50, ma200, realized_vol_20d, spy_price "
                "FROM regime_history ORDER BY date DESC LIMIT 1"
            )
            row = cur.fetchone()

        if row:
            return {
                "regime": row[0],
                "confidence": float(row[1]) if row[1] is not None else None,
                "source": "hmm",
                "ma50": float(row[2]) if row[2] is not None else None,
                "ma200": float(row[3]) if row[3] is not None else None,
                "realized_vol_20d": float(row[4]) if row[4] is not None else None,
                "spy_price": float(row[5]) if row[5] is not None else None,
            }
    except Exception:
        # regime_history table may not exist yet
        pass

    # Fallback: MA-crossover rules on SPY
    closes: list[float] = []
    try:
        with conn() as c, c.cursor() as cur:
            cur.execute(
                "SELECT close FROM ohlcv_daily WHERE ticker = 'SPY' "
                "ORDER BY date DESC LIMIT 250"
            )
            rows = cur.fetchall()
        closes = [float(r[0]) for r in rows][::-1]  # ascending
    except Exception:
        pass

    if len(closes) < 200:
        try:
            df = yf.download("SPY", period="2y", auto_adjust=True, progress=False)
            if not df.empty:
                closes = [float(v) for v in df["Close"].dropna().tolist()]
        except Exception:
            pass

    if len(closes) < 200:
        return {
            "regime": "unknown",
            "confidence": None,
            "source": "none",
            "ma50": None,
            "ma200": None,
            "realized_vol_20d": None,
            "spy_price": None,
        }

    ma50 = sum(closes[-50:]) / 50
    ma200 = sum(closes[-200:]) / 200
    regime = _classify(ma50, ma200)
    vol = _realized_vol(closes)
    spy_price = closes[-1]

    return {
        "regime": regime,
        "confidence": None,
        "source": "ma_rules",
        "ma50": round(ma50, 4),
        "ma200": round(ma200, 4),
        "realized_vol_20d": round(vol, 6) if vol is not None else None,
        "spy_price": round(spy_price, 4),
    }
