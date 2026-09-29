"""Position sizing — volatility tier caps and correlation multipliers."""
from __future__ import annotations

import math

from src.core.logging import get_logger

log = get_logger(__name__)


def volatility_tier_cap(vol_60d: float) -> float:
    """Return position cap based on 60-day annualized volatility.

    <10%  -> 0.05
    <20%  -> 0.04
    <30%  -> 0.03
    >=30% -> 0.02
    """
    if vol_60d < 0.10:
        return 0.05
    if vol_60d < 0.20:
        return 0.04
    if vol_60d < 0.30:
        return 0.03
    return 0.02


def correlation_multiplier(corr: float) -> float:
    """Scale down position size when correlation with portfolio is high.

    corr <= 0.5              -> 1.0
    0.5 < corr <= 0.8        -> linear interpolation from 1.0 to 0.7
    corr > 0.8               -> 0.7
    """
    if corr <= 0.5:
        return 1.0
    if corr > 0.8:
        return 0.7
    # Linear: at corr=0.5 -> 1.0, at corr=0.8 -> 0.7
    # slope = (0.7 - 1.0) / (0.8 - 0.5) = -1.0
    return 1.0 + (corr - 0.5) * (-1.0)


def compute_max_shares(
    ticker: str,
    portfolio_value: float,
    price: float,
    vol_60d: float,
    corr: float,
) -> int:
    """Compute maximum number of shares to hold for a given ticker.

    floor(vol_cap * corr_mult * portfolio_value / price). Minimum 0.
    """
    if price <= 0 or portfolio_value <= 0:
        log.warning(
            "compute_max_shares: invalid price or portfolio_value",
            ticker=ticker,
            price=price,
            portfolio_value=portfolio_value,
        )
        return 0

    vol_cap = volatility_tier_cap(vol_60d)
    corr_mult = correlation_multiplier(corr)
    max_value = vol_cap * corr_mult * portfolio_value
    shares = max(0, math.floor(max_value / price))
    log.debug("compute_max_shares", ticker=ticker, vol_cap=vol_cap, corr_mult=corr_mult, max_shares=shares)
    return shares
