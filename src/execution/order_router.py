"""
Smart order router with limit escalation.
Strategy: limit → aggressive limit → IOC → log UNFILLED
No market orders are ever submitted.
"""
from __future__ import annotations

import time
from src.execution.broker import submit_limit_order, cancel_order, get_order_status, get_filled_price
from src.core.logging import get_logger
from src.risk.pretrade import OrderIntent, check_equity_order
from dashboard_api.routers.kill_switch import is_paused

logger = get_logger(__name__)

# Escalation configuration
WAIT_SECONDS = 30
AGGRESSIVE_SPREAD_MULT_BUY = 1.0025   # +0.25% for aggressive buy
AGGRESSIVE_SPREAD_MULT_SELL = 0.9975  # -0.25% for aggressive sell
IOC_SPREAD_MULT_BUY = 1.005           # +0.5% IOC buy
IOC_SPREAD_MULT_SELL = 0.995          # -0.5% IOC sell


def _wait_for_fill(order_id: str, wait_seconds: int = WAIT_SECONDS) -> bool:
    """Poll order status until filled or timeout. Returns True if filled."""
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        status = get_order_status(order_id)
        if status and "filled" in status.lower():
            return True
        if status and status in ("canceled", "expired", "rejected"):
            return False
        time.sleep(2)
    return False


def route_order(
    ticker: str,
    side: str,   # "buy" | "sell"
    qty: int,
    target_price: float,
) -> dict | None:
    """
    Route an order through the escalation ladder:
    1. Limit at target_price → wait 30s
    2. Aggressive limit (±0.25%) → wait 30s
    3. IOC limit (±0.5%) → 1 attempt
    4. Log UNFILLED

    Returns order result dict with {order_id, fill_price, side, qty, ticker} or None if unfilled.
    Checks kill switch before any submission.
    """
    if is_paused():
        logger.info(f"Kill switch active — blocking order for {ticker}")
        return None

    if qty <= 0:
        return None

    # Single fail-closed pre-trade gate. Runs once per logical order; the
    # escalation steps below are the same approved intent at bounded (±0.5%)
    # prices, well inside the collar, so they don't re-gate.
    decision = check_equity_order(
        OrderIntent(symbol=ticker, side=side, qty=qty, limit_price=target_price, asset_class="equity")
    )
    if not decision.allow:
        logger.warning(f"[route] pre-trade gate REJECTED {side} {qty}x{ticker}: {decision.reason}")
        return None

    # Step 1: Limit at target price
    logger.info(f"[route] Step 1: limit {side} {qty}x{ticker} @ {target_price:.2f}")
    order = submit_limit_order(ticker, qty, side, target_price, "day")
    if order:
        if _wait_for_fill(order["order_id"], WAIT_SECONDS):
            fill_price = get_filled_price(order["order_id"])
            return {**order, "fill_price": fill_price, "escalation_step": 1}
        cancel_order(order["order_id"])

    # Step 2: Aggressive limit
    if is_paused():
        logger.info(f"Kill switch active — aborting escalation for {ticker} before step 2")
        return None

    if side == "buy":
        aggressive_price = target_price * AGGRESSIVE_SPREAD_MULT_BUY
    else:
        aggressive_price = target_price * AGGRESSIVE_SPREAD_MULT_SELL

    logger.info(f"[route] Step 2: aggressive limit {side} {qty}x{ticker} @ {aggressive_price:.2f}")
    order = submit_limit_order(ticker, qty, side, aggressive_price, "day")
    if order:
        if _wait_for_fill(order["order_id"], WAIT_SECONDS):
            fill_price = get_filled_price(order["order_id"])
            return {**order, "fill_price": fill_price, "escalation_step": 2}
        cancel_order(order["order_id"])

    # Step 3: IOC limit
    if is_paused():
        logger.info(f"Kill switch active — aborting escalation for {ticker} before step 3")
        return None

    if side == "buy":
        ioc_price = target_price * IOC_SPREAD_MULT_BUY
    else:
        ioc_price = target_price * IOC_SPREAD_MULT_SELL

    logger.info(f"[route] Step 3: IOC limit {side} {qty}x{ticker} @ {ioc_price:.2f}")
    order = submit_limit_order(ticker, qty, side, ioc_price, "ioc")
    if order:
        time.sleep(3)  # IOC fills or dies quickly
        status = get_order_status(order["order_id"])
        if status and "filled" in status.lower():
            fill_price = get_filled_price(order["order_id"])
            return {**order, "fill_price": fill_price, "escalation_step": 3}

    # Step 4: UNFILLED
    logger.warning(f"[route] UNFILLED: {side} {qty}x{ticker} @ {target_price:.2f} after 3 escalation steps")
    return None
