"""QLib-style alpha model: load, predict, and upsert signals."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from src.core.db import conn
from src.core.logging import get_logger

log = get_logger(__name__)

MODEL_PATH = Path(__file__).resolve().parents[3] / "models" / "qlib" / "model.pkl"

FEATURE_COLS = [
    "mom_5d", "mom_20d", "mom_60d",
    "vol_20d", "vol_60d",
    "rev_5d",
    "turnover_20d",
    "pe_ratio_norm",
    "market_cap_log",
]


def load_model(model_path: "Path | None" = None) -> "lgb.Booster | None":
    """Load model from model_path (default MODEL_PATH). Return None if file missing."""
    import lightgbm as lgb

    path = model_path or MODEL_PATH
    if not path.exists():
        log.info("load_model: model file not found", path=str(path))
        return None
    booster = lgb.Booster(model_file=str(path))
    log.info("load_model: loaded", path=str(path))
    return booster


def predict_alpha(
    tickers: list[str], as_of_date: str, model_path: "Path | None" = None
) -> dict[str, float]:
    """Build features for as_of_date, predict, normalize to [-1, 1]. Return {ticker: score}."""
    from src.strategy.alpha.features import build_alpha_features

    model = load_model(model_path)
    if model is None:
        log.warning("predict_alpha: no model available, returning empty scores")
        return {}

    # Build features using a window ending at as_of_date (90 days of history for rolling calcs)
    end_dt = pd.Timestamp(as_of_date)
    start_dt = end_dt - pd.Timedelta(days=90)
    df = build_alpha_features(tickers, start_dt.date().isoformat(), end_dt.date().isoformat())

    if df.empty:
        log.warning("predict_alpha: empty feature df", date=as_of_date)
        return {}

    # Filter to the requested date only
    try:
        day_df = df.xs(end_dt, level="date")
    except KeyError:
        # Try to find the closest available date
        dates_available = df.index.get_level_values("date").unique()
        if len(dates_available) == 0:
            return {}
        closest = dates_available[dates_available <= end_dt].max()
        if pd.isna(closest):
            return {}
        day_df = df.xs(closest, level="date")

    if day_df.empty:
        return {}

    X = day_df[FEATURE_COLS].fillna(0).values
    # num_threads=1: see training.py — avoids OpenMP runtime conflicts with
    # torch/hmmlearn already loaded in this process.
    raw_scores = model.predict(X, num_threads=1)

    # Normalize to [-1, 1] using rank normalization
    n = len(raw_scores)
    if n == 1:
        scores_norm = np.array([0.0])
    else:
        ranks = pd.Series(raw_scores).rank(pct=True)
        scores_norm = (ranks.values * 2 - 1).clip(-1, 1)

    result = {ticker: float(score) for ticker, score in zip(day_df.index.tolist(), scores_norm)}
    log.info("predict_alpha: predicted", tickers=len(result), date=as_of_date)
    return result


def get_alpha_scores(tickers: list[str]) -> dict[str, float]:
    """Load model (train if missing). Predict for today. Return scores."""
    from src.strategy.alpha.training import train_model

    if not MODEL_PATH.exists():
        log.info("get_alpha_scores: model missing, training now")
        train_model()

    today = date.today().isoformat()
    return predict_alpha(tickers, today)


def run_alpha_pipeline(tickers: list[str]) -> int:
    """Get scores, upsert signal_name='qlib_alpha' to signals table. Return count."""
    scores = get_alpha_scores(tickers)
    if not scores:
        log.warning("run_alpha_pipeline: no scores generated")
        return 0

    today = date.today().isoformat()
    upsert_sql = """
        INSERT INTO signals (ticker, date, signal_name, value, confidence)
        VALUES (%(ticker)s, %(date)s, 'qlib_alpha', %(value)s, 0.6)
        ON CONFLICT (ticker, date, signal_name)
        DO UPDATE SET value = EXCLUDED.value, confidence = EXCLUDED.confidence
    """

    count = 0
    with conn() as c, c.cursor() as cur:
        for ticker, value in scores.items():
            cur.execute(upsert_sql, {"ticker": ticker, "value": value, "date": today})
            count += 1
        c.commit()

    log.info("run_alpha_pipeline: upserted signals", count=count)
    return count


def _model_reset() -> None:
    """Delete MODEL_PATH (for testing)."""
    if MODEL_PATH.exists():
        MODEL_PATH.unlink()
        log.info("_model_reset: model file deleted", path=str(MODEL_PATH))
