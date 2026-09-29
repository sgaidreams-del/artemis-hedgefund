"""Wash sale detection per IRS rules."""
from __future__ import annotations

from datetime import date, timedelta

from src.core.logging import get_logger

log = get_logger(__name__)


def would_trigger_wash_sale(
    ticker: str,
    sale_date: date,
    lots: list,
    sale_price: float,
) -> bool:
    """Determine if a sale would trigger a wash sale under IRS rules.

    Wash sale ONLY applies to LOSS sales.
    - If selling at a gain (sale_price > cost_basis), return False immediately.
    - If selling at a loss: return True if any lot was acquired within 30 days
      of sale_date (before or after).
    """
    # Check if ANY lot is being sold at a loss; use the first lot's cost_basis
    # as a proxy, or check if sale_price < any lot's cost_basis.
    # Per spec: if selling at GAIN, return False immediately.
    # We check if sale_price > average cost_basis as the gain check.
    if not lots:
        return False

    # Determine if this is a loss sale: any lot where cost_basis > sale_price
    has_loss = any(lot.cost_basis > sale_price for lot in lots)
    if not has_loss:
        log.debug("would_trigger_wash_sale: gain sale, no wash sale risk", ticker=ticker)
        return False

    # Wash sale window: 30 days before or after sale_date
    window_start = sale_date - timedelta(days=30)
    window_end = sale_date + timedelta(days=30)

    for lot in lots:
        acquired = lot.acquired_date
        if window_start <= acquired <= window_end:
            log.warning(
                "would_trigger_wash_sale: wash sale triggered",
                ticker=ticker,
                sale_date=sale_date.isoformat(),
                lot_acquired=acquired.isoformat(),
            )
            return True

    return False


def intentional_wash_ok(ticker: str, alpha: float) -> bool:
    """Return True if expected alpha > 0.5% (worth taking wash sale penalty)."""
    threshold = 0.005
    ok = alpha > threshold
    log.debug("intentional_wash_ok", ticker=ticker, alpha=alpha, ok=ok)
    return ok
