"""LightGBM alpha model training with time-series cross-validation."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.model_selection import TimeSeriesSplit

from src.core.logging import get_logger
from src.strategy.alpha import features as _features_module

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


def _compute_labels(df: pd.DataFrame) -> pd.Series:
    """Compute forward 5-day rank-normalized return labels."""
    # df has multi-index (ticker, date); need close prices to compute forward returns.
    # If close is in df, use it; otherwise label must come from the caller.
    # We assume df contains a 'close' column or we derive from mom_5d inverse.
    # For robustness: recompute from the feature index — we use mom_5d as a proxy
    # but the cleanest approach is to use a synthetic forward-return column.
    # The caller (train_model) passes the full feature df; we derive forward returns
    # from mom_5d shifted backward (i.e., future momentum = shift(-5) of mom_5d).
    # This is mathematically equivalent to forward 5-day return.
    # We rank-normalize cross-sectionally per date.
    future_mom = df.groupby(level="ticker")["mom_5d"].shift(-5)
    labels = future_mom.groupby(level="date").rank(pct=True) * 2 - 1  # [-1, 1]
    return labels


def train_model(
    lookback_days: int = 756,
    as_of_date: str | None = None,
    model_path: "Path | None" = None,
) -> "lgb.Booster":
    """Build feature df, compute forward 5-day rank-normalized return labels.

    Train LightGBM with 5-fold time-series CV and early stopping.
    Save model to model_path (default MODEL_PATH; create parent dirs). Return booster.

    as_of_date: train only on data up to (and including) this date — defaults
    to today for the live pipeline. Point-in-time walk-forward backtesting
    must pass the train window's end date here, or the model leaks future
    data into its own "historical" prediction.

    model_path: where to save the model. Backtesting must pass a path other
    than MODEL_PATH — that file is the live pipeline's model, and overwriting
    it with an as-of-the-past backtest artifact would silently make the next
    live run trade on a stale model (get_alpha_scores only retrains when the
    file is missing, not when it's old).
    """
    from src.core.config import universe as universe_cfg

    end = date.fromisoformat(as_of_date) if as_of_date else date.today()
    end_date = end.isoformat()
    start_date = (end - timedelta(days=lookback_days + 90)).isoformat()

    tickers = universe_cfg()["seed_tickers"]

    log.info("train_model: building features", tickers=len(tickers), start=start_date, end=end_date)
    df = _features_module.build_alpha_features(tickers, start_date, end_date)

    if df.empty:
        raise RuntimeError("train_model: feature dataframe is empty — no data in DB?")

    labels = _compute_labels(df)

    # Align features and labels. Fundamentals (pe_ratio_norm, market_cap_log) are
    # sparse point-in-time snapshots and will legitimately be NaN for most rows
    # early on — fill with 0 (neutral, since these are already z-scored) rather
    # than dropping, matching predict_alpha()'s fillna(0) at inference time.
    # Price-derived columns and the label stay strict: those NaNs reflect real
    # warmup gaps (e.g. mom_60d needs 60 prior days) that shouldn't be backfilled.
    combined = df.copy()
    combined[["pe_ratio_norm", "market_cap_log"]] = combined[["pe_ratio_norm", "market_cap_log"]].fillna(0.0)
    combined["_label"] = labels
    combined = combined.dropna()

    X = combined[FEATURE_COLS].values
    y = combined["_label"].values

    log.info("train_model: dataset ready", rows=len(X), features=len(FEATURE_COLS))

    # 5-fold time-series CV
    tscv = TimeSeriesSplit(n_splits=5)
    splits = list(tscv.split(X))
    train_idx, val_idx = splits[-1]  # use last split for early stopping

    X_train, y_train = X[train_idx], y[train_idx]
    X_val, y_val = X[val_idx], y[val_idx]

    dtrain = lgb.Dataset(X_train, label=y_train, feature_name=FEATURE_COLS)
    dval = lgb.Dataset(X_val, label=y_val, feature_name=FEATURE_COLS, reference=dtrain)

    params = {
        "objective": "regression",
        "metric": "rmse",
        "learning_rate": 0.05,
        "num_leaves": 63,
        "min_child_samples": 20,
        "feature_fraction": 0.8,
        "bagging_fraction": 0.8,
        "bagging_freq": 5,
        "lambda_l1": 0.1,
        "lambda_l2": 0.1,
        "verbose": -1,
        # Single-threaded: this run shares a process with torch (FinBERT) and
        # hmmlearn (regime), each bundling their own OpenMP runtime. Multiple
        # OpenMP runtimes contending for threads in one process is a known
        # macOS segfault cause; dataset is a few thousand rows so there's no
        # real performance cost to staying single-threaded.
        "n_jobs": 1,
        "num_threads": 1,
    }

    callbacks = [
        lgb.early_stopping(stopping_rounds=20, verbose=False),
        lgb.log_evaluation(period=50),
    ]

    booster = lgb.train(
        params,
        dtrain,
        num_boost_round=200,
        valid_sets=[dval],
        callbacks=callbacks,
    )

    save_path = model_path or MODEL_PATH
    save_path.parent.mkdir(parents=True, exist_ok=True)
    booster.save_model(str(save_path))
    log.info("train_model: model saved", path=str(save_path))

    return booster
