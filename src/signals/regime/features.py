"""Regime feature engineering — pulls SPY OHLCV from DB and computes rolling vol features."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.core.db import conn
from src.core.logging import get_logger, log_activity

logger = get_logger(__name__)


def build_regime_features(n_days: int = 500) -> pd.DataFrame:
    """Pull SPY from ohlcv_daily, compute (log_return, vol_20d, vol_5d, vol_ratio=vol_5d/vol_20d).

    Returns df indexed by date with these 4 columns.
    vol_ratio = vol_5d/vol_20d.
    Minimum: n_days+50 rows of raw price data fetched so there's enough history for rolling windows.
    """
    fetch_rows = n_days + 50

    with conn() as c, c.cursor() as cur:
        cur.execute(
            """
            SELECT date, close
            FROM ohlcv_daily
            WHERE ticker = 'SPY'
            ORDER BY date DESC
            LIMIT %s
            """,
            (fetch_rows,),
        )
        rows = cur.fetchall()

    if not rows:
        raise ValueError("No SPY data found in ohlcv_daily")

    df = pd.DataFrame(rows, columns=["date", "close"])
    df = df.sort_values("date").set_index("date")
    df.index = pd.to_datetime(df.index)
    df["close"] = df["close"].astype(float)

    df["log_return"] = np.log(df["close"] / df["close"].shift(1))
    df["vol_20d"] = df["log_return"].rolling(20).std()
    df["vol_5d"] = df["log_return"].rolling(5).std()
    df["vol_ratio"] = df["vol_5d"] / df["vol_20d"]

    features = df[["log_return", "vol_20d", "vol_5d", "vol_ratio"]].dropna()
    features = features.tail(n_days)

    log_activity(
        component="regime.features",
        action="build_regime_features",
        rows=len(features),
        n_days=n_days,
    )
    logger.info("regime_features_built", rows=len(features))
    return features
