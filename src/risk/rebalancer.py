"""Portfolio rebalancer — compute orders needed to reach target weights."""
from __future__ import annotations

import math

from src.core.logging import get_logger

log = get_logger(__name__)


def compute_rebalance_orders(
    current: dict,
    target_weights: dict,
    portfolio_value: float,
    threshold: float = 0.005,
    max_shares_map: dict | None = None,
) -> list[dict]:
    """Generate rebalance orders to move current positions toward target weights.

    Args:
        current: {ticker: {"qty": int, "price": float, "market_value": float}}
        target_weights: {ticker: float} target allocation weights (0 to 1)
        portfolio_value: total portfolio value in dollars
        threshold: minimum drift to trigger a rebalance order (default 0.5%)
        max_shares_map: optional {ticker: int} cap on shares held

    Returns:
        list of {ticker, side, qty, reason}

    Raises:
        ValueError: if a current position is missing the 'price' key.
    """
    if portfolio_value <= 0:
        log.warning("compute_rebalance_orders: portfolio_value <= 0, no orders generated")
        return []

    # Validate that all current positions have 'price'
    for ticker, pos in current.items():
        if "price" not in pos:
            raise ValueError(f"Position for {ticker!r} is missing required 'price' key")

    orders = []
    all_tickers = set(current.keys()) | set(target_weights.keys())

    for ticker in all_tickers:
        pos = current.get(ticker, {})
        target_weight = target_weights.get(ticker, 0.0)
        current_value = pos.get("market_value", 0.0)
        price = pos.get("price", 0.0)

        # For new positions not in current, price may be in target_weights context
        # If price is 0 (not held and no price known), skip
        if price <= 0 and ticker not in current:
            log.debug("compute_rebalance_orders: no price for new ticker, skipping", ticker=ticker)
            continue

        current_weight = current_value / portfolio_value if portfolio_value > 0 else 0.0
        drift = target_weight - current_weight

        if abs(drift) <= threshold:
            log.debug("compute_rebalance_orders: drift within threshold", ticker=ticker, drift=drift)
            continue

        # Compute target shares
        target_value = target_weight * portfolio_value
        if price <= 0:
            log.warning("compute_rebalance_orders: zero price for ticker, skipping", ticker=ticker)
            continue

        target_shares = math.floor(target_value / price)
        current_shares = pos.get("qty", 0)
        delta_shares = target_shares - current_shares

        # Apply max_shares cap
        if max_shares_map and ticker in max_shares_map:
            max_shares = max_shares_map[ticker]
            if target_shares > max_shares:
                log.debug("compute_rebalance_orders: capping at max_shares", ticker=ticker, target_shares=target_shares, max_shares=max_shares)
                target_shares = max_shares
                delta_shares = target_shares - current_shares

        if delta_shares == 0:
            continue

        side = "buy" if delta_shares > 0 else "sell"
        qty = abs(delta_shares)

        orders.append({
            "ticker": ticker,
            "side": side,
            "qty": qty,
            "reason": f"rebalance drift={drift:+.4f} target_weight={target_weight:.4f}",
        })
        log.info(
            "compute_rebalance_orders: order generated",
            ticker=ticker,
            side=side,
            qty=qty,
            drift=drift,
        )

    return orders
