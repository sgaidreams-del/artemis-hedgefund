"""Cumulative Abnormal Return computation for event study."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.core.logging import get_logger
from src.validation.event_study.market_model import fit_market_model

log = get_logger(__name__)


def compute_car(
    stock_returns: pd.Series,
    market_returns: pd.Series,
    event_date: str,
    pre_days: int = 5,
    post_days: int = 20,
) -> dict:
    """Compute Cumulative Abnormal Return around event_date.

    Uses a pre-event estimation window (everything before event_date minus pre_days)
    to fit the market model, then computes abnormal returns over the event window
    [event_date - pre_days, event_date + post_days].

    Returns
    -------
    dict with keys: car, aar_series (pd.Series), event_window_returns (pd.Series),
                    model_params (dict)
    """
    aligned = pd.concat(
        [stock_returns.rename("stock"), market_returns.rename("market")], axis=1
    ).dropna()
    aligned.index = pd.to_datetime(aligned.index)
    event_ts = pd.Timestamp(event_date)

    if event_ts not in aligned.index:
        # Find nearest trading day at or after event_date
        candidates = aligned.index[aligned.index >= event_ts]
        if len(candidates) == 0:
            raise ValueError(f"event_date {event_date} is after all available data")
        event_ts = candidates[0]
        log.warning("car.event_date_adjusted", adjusted_to=str(event_ts))

    event_pos = aligned.index.get_loc(event_ts)

    # Estimation window: all data before the event window
    est_end = event_pos - pre_days
    if est_end < 30:
        raise ValueError("Insufficient data before event window for estimation")

    est_data = aligned.iloc[:est_end]
    model_params = fit_market_model(est_data["stock"], est_data["market"])

    # Event window
    win_start = max(0, event_pos - pre_days)
    win_end = min(len(aligned), event_pos + post_days + 1)
    event_window = aligned.iloc[win_start:win_end]

    # Abnormal returns = actual - (alpha + beta * market)
    alpha = model_params["alpha"]
    beta = model_params["beta"]
    expected = alpha + beta * event_window["market"]
    abnormal = event_window["stock"] - expected

    car = float(abnormal.sum())
    aar = abnormal  # average abnormal return series (daily)

    log.info(
        "car.computed",
        event_date=str(event_ts),
        car=round(car, 6),
        n_days=len(event_window),
    )

    return {
        "car": car,
        "aar_series": aar,
        "event_window_returns": event_window["stock"],
        "model_params": model_params,
    }
