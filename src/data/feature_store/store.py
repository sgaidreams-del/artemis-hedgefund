"""Feature store — compute features once, serve many times. SPEC §4.5.

STATUS: skeleton. The first computed feature is a simple 20-day momentum
to prove the pipeline end-to-end. AutoResearch + Phase 2 will expand this.
"""
from __future__ import annotations

from datetime import date, timedelta

from ...core.db import conn
from ...core.logging import get_logger, log_activity

log = get_logger("feature_store")


def compute_daily() -> dict:
    """Recompute features for today across the universe.

    Initial feature set:
      - mom_20d  : (close_today - close_20d_ago) / close_20d_ago
      - vol_20d  : 20-day stdev of daily returns
      - close    : passthrough (handy for downstream joins)
    """
    today = date.today()
    cutoff = today - timedelta(days=60)
    inserted = 0
    with conn() as c, c.cursor() as cur:
        # Pull recent prices
        cur.execute(
            """
            WITH ret AS (
              SELECT ticker, date, close,
                     close / NULLIF(LAG(close, 1) OVER (PARTITION BY ticker ORDER BY date), 0) - 1 AS daily_ret
              FROM ohlcv_daily
              WHERE date >= %s
            ),
            base AS (
              SELECT ticker, date, close,
                     LAG(close, 20) OVER (PARTITION BY ticker ORDER BY date) AS close_20d_ago,
                     STDDEV(daily_ret)
                       OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS vol_20d
              FROM ret
            )
            SELECT ticker, date, close, close_20d_ago, vol_20d FROM base WHERE date = %s
            """,
            (cutoff, today),
        )
        rows = cur.fetchall()
        for ticker, d, close, c20, vol in rows:
            if close is None:
                continue
            features = {"close": float(close)}
            if c20 and float(c20) > 0:
                features["mom_20d"] = (float(close) - float(c20)) / float(c20)
            if vol is not None:
                features["vol_20d"] = float(vol)
            for name, value in features.items():
                cur.execute(
                    """
                    INSERT INTO features_daily (ticker, date, feature_name, value)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (ticker, date, feature_name) DO UPDATE SET value=EXCLUDED.value
                    """,
                    (ticker, d, name, value),
                )
                inserted += 1
        c.commit()
    log_activity("feature_store", "compute_daily", "ok", rows=inserted)
    return {"rows": inserted, "date": str(today)}
