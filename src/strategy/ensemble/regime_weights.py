"""Regime-conditional weight multipliers for the signal ensemble."""
from __future__ import annotations

from src.core.logging import get_logger

log = get_logger("ensemble.regime_weights")

# Multipliers applied on top of the base weights for each market regime.
# Keys not listed keep a multiplier of 1.0 (unchanged).
REGIME_WEIGHT_OVERRIDES: dict[str, dict[str, float]] = {
    "Bull/Low-Vol": {
        "sentiment_1d": 1.2,
        "technical_composite": 1.1,
        "short_interest_signal": 0.8,
    },
    "Bull/High-Vol": {
        "sentiment_1d": 1.0,
        "technical_composite": 0.9,
        "options_flow_signal": 1.2,
    },
    "Bear/Low-Vol": {
        "insider_signal": 1.3,
        "llm_sentiment": 1.2,
        "technical_composite": 0.7,
    },
    "Bear/High-Vol": {
        "insider_signal": 1.1,
        "short_interest_signal": 1.3,
        "technical_composite": 0.6,
    },
    "Sideways": {
        "insider_signal": 1.0,
        "technical_composite": 1.0,
    },
}


def apply_regime_overrides(base_weights: dict[str, float], regime: str) -> dict[str, float]:
    """Multiply base weights by regime-specific multipliers, then renormalise to sum=1.

    Parameters
    ----------
    base_weights:
        Mapping of signal_name -> weight (need not sum to 1).
    regime:
        One of the keys in REGIME_WEIGHT_OVERRIDES, or any arbitrary string
        (unrecognised regimes return a copy of the base weights, renormalised).

    Returns
    -------
    dict[str, float]
        Renormalised weights that sum to 1.0 (or empty dict if base is empty).
    """
    overrides = REGIME_WEIGHT_OVERRIDES.get(regime, {})

    adjusted: dict[str, float] = {}
    for name, w in base_weights.items():
        multiplier = overrides.get(name, 1.0)
        adjusted[name] = w * multiplier

    total = sum(adjusted.values())
    if total <= 0:
        log.warning("apply_regime_overrides: total weight <= 0 for regime=%s", regime)
        return {k: 0.0 for k in adjusted}

    return {k: v / total for k, v in adjusted.items()}
