"""Cross-sectional alpha features built from ohlcv_daily + features_daily."""
from __future__ import annotations

import pandas as pd
import numpy as np

from src.core.db import conn
from src.core.logging import get_logger

log = get_logger(__name__)


def build_alpha_features(tickers: list[str], start_date: str, end_date: str) -> pd.DataFrame:
    """Read ohlcv_daily + features_daily. Return multi-index (ticker, date) DataFrame.

    Columns: mom_5d, mom_20d, mom_60d, vol_20d, vol_60d, rev_5d,
             turnover_20d, pe_ratio_norm, market_cap_log.
    Cross-sectionally z-score each column per date.
    """
    ohlcv_sql = """
        SELECT ticker, date, open, high, low, close, volume
        FROM ohlcv_daily
        WHERE ticker = ANY(%(tickers)s)
          AND date BETWEEN %(start_date)s AND %(end_date)s
        ORDER BY ticker, date
    """
    features_sql = """
        SELECT ticker, asof_date AS date, pe_ratio, market_cap
        FROM fundamentals
        WHERE ticker = ANY(%(tickers)s)
          AND asof_date BETWEEN %(start_date)s AND %(end_date)s
        ORDER BY ticker, asof_date
    """

    params = {"tickers": tickers, "start_date": start_date, "end_date": end_date}

    with conn() as c, c.cursor() as cur:
        cur.execute(ohlcv_sql, params)
        ohlcv_rows = cur.fetchall()
        ohlcv_cols = [desc[0] for desc in cur.description]

    with conn() as c, c.cursor() as cur:
        cur.execute(features_sql, params)
        feat_rows = cur.fetchall()
        feat_cols = [desc[0] for desc in cur.description]

    ohlcv = pd.DataFrame(ohlcv_rows, columns=ohlcv_cols)
    feats = pd.DataFrame(feat_rows, columns=feat_cols)

    if ohlcv.empty:
        log.warning("build_alpha_features: no OHLCV data returned", tickers=tickers)
        return pd.DataFrame()

    # psycopg3 returns NUMERIC columns as Decimal; numpy ufuncs need float64.
    # to_numeric (not astype) since pe_ratio/market_cap may be NULL.
    for col in ("open", "high", "low", "close", "volume"):
        ohlcv[col] = pd.to_numeric(ohlcv[col], errors="coerce")
    if not feats.empty:
        for col in ("pe_ratio", "market_cap"):
            feats[col] = pd.to_numeric(feats[col], errors="coerce")

    ohlcv["date"] = pd.to_datetime(ohlcv["date"])
    ohlcv = ohlcv.sort_values(["ticker", "date"])

    # --- Compute raw features using vectorized ops ---
    g = ohlcv.groupby("ticker", sort=False)["close"]

    # Momentum: pct change over N days
    ohlcv["mom_5d"] = g.pct_change(5)
    ohlcv["mom_20d"] = g.pct_change(20)
    ohlcv["mom_60d"] = g.pct_change(60)

    # Reversal: negative of 5-day momentum (short-term mean reversion)
    ohlcv["rev_5d"] = -ohlcv["mom_5d"]

    # Realized volatility: rolling std of log returns
    log_ret = g.transform(lambda s: np.log(s / s.shift(1)))
    ohlcv["vol_20d"] = log_ret.groupby(ohlcv["ticker"]).transform(
        lambda s: s.rolling(20, min_periods=10).std()
    )
    ohlcv["vol_60d"] = log_ret.groupby(ohlcv["ticker"]).transform(
        lambda s: s.rolling(60, min_periods=30).std()
    )

    # Turnover: rolling mean of volume (20-day)
    ohlcv["turnover_20d"] = ohlcv.groupby("ticker", sort=False)["volume"].transform(
        lambda s: s.rolling(20, min_periods=10).mean()
    )

    # Merge fundamental features as-of each price date — fundamentals are sparse
    # point-in-time snapshots, not daily series, so an exact-date join would only
    # ever match the handful of days a snapshot happens to land on. Carry the most
    # recent known snapshot forward per ticker instead.
    if not feats.empty:
        feats["date"] = pd.to_datetime(feats["date"])
        feats = feats.sort_values(["date", "ticker"])
        # merge_asof requires the "on" key globally sorted, even when using "by"
        ohlcv = pd.merge_asof(
            ohlcv.sort_values(["date", "ticker"]),
            feats[["ticker", "date", "pe_ratio", "market_cap"]],
            on="date",
            by="ticker",
            direction="backward",
        )
    else:
        ohlcv["pe_ratio"] = np.nan
        ohlcv["market_cap"] = np.nan

    # PE ratio normalization (cross-sectional z-score applied below)
    ohlcv["pe_ratio_norm"] = ohlcv["pe_ratio"]

    # Market cap log transform
    ohlcv["market_cap_log"] = np.log1p(ohlcv["market_cap"].clip(lower=0))

    # --- Set multi-index ---
    feature_cols = [
        "mom_5d", "mom_20d", "mom_60d",
        "vol_20d", "vol_60d",
        "rev_5d",
        "turnover_20d",
        "pe_ratio_norm",
        "market_cap_log",
    ]
    ohlcv = ohlcv.set_index(["ticker", "date"])
    df = ohlcv[feature_cols].copy()

    # --- Cross-sectional z-score per date ---
    def _cs_zscore(x: pd.Series) -> pd.Series:
        mu = x.mean()
        sigma = x.std()
        if sigma == 0 or pd.isna(sigma):
            return x - mu
        return (x - mu) / sigma

    df = df.groupby(level="date", group_keys=False).transform(_cs_zscore)

    log.info("build_alpha_features: complete", rows=len(df), tickers=len(tickers))
    return df
