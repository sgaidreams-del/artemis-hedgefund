"""Sandbox signal generator — creates synthetic signal DataFrames for hypothesis testing."""
from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from src.core.logging import get_logger

log = get_logger(__name__)

# Signal type → (mean_return_per_day, daily_vol) parameters
_SIGNAL_PARAMS: dict[str, tuple[float, float]] = {
    "momentum": (0.0004, 0.012),
    "mean_reversion": (-0.0002, 0.010),
    "sentiment": (0.0003, 0.015),
    "macro": (0.0002, 0.008),
    "technical": (0.0003, 0.011),
    "alternative": (0.0005, 0.018),
}
_DEFAULT_PARAMS = (0.0003, 0.012)


def create_sandbox_signals(hypothesis: dict, n_days: int = 252) -> pd.DataFrame:
    """Generate a synthetic signal DataFrame for the hypothesis spec.

    The random seed is derived from the hypothesis id so results are
    reproducible per hypothesis.

    Returns a DataFrame with columns:
        date, signal, returns, position
    """
    h_id = hypothesis.get("id", "unknown")
    signal_type = hypothesis.get("signal_type", "technical")
    expected_alpha = float(hypothesis.get("expected_alpha", 0.03))

    # Deterministic seed from hypothesis id
    seed = int(hashlib.sha256(h_id.encode()).hexdigest()[:8], 16) % (2**31)
    rng = np.random.default_rng(seed)

    mu, sigma = _SIGNAL_PARAMS.get(signal_type, _DEFAULT_PARAMS)
    # Blend in expected_alpha
    mu = (mu + expected_alpha / 252) / 2

    dates = pd.bdate_range(end=pd.Timestamp.today(), periods=n_days)

    # Raw signal: autocorrelated noise
    signal_raw = rng.standard_normal(n_days)
    # Mild AR(1) to simulate persistence
    for i in range(1, n_days):
        signal_raw[i] = 0.3 * signal_raw[i - 1] + 0.7 * signal_raw[i]
    signal_z = (signal_raw - signal_raw.mean()) / (signal_raw.std() + 1e-9)

    # Positions: sign of signal
    positions = np.sign(signal_z)

    # Returns: drift + noise, scaled by position
    noise = rng.normal(0, sigma, n_days)
    returns = positions * (mu + noise)

    df = pd.DataFrame(
        {
            "date": dates,
            "signal": signal_z,
            "returns": returns,
            "position": positions,
        }
    )
    df["cumulative_returns"] = (1 + df["returns"]).cumprod()

    log.info(
        "create_sandbox_signals",
        hypothesis_id=h_id,
        signal_type=signal_type,
        n_days=n_days,
        total_return=round(float(df["cumulative_returns"].iloc[-1] - 1), 4),
    )
    return df
