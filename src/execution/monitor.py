"""Execution quality monitoring — slippage tracking."""
from __future__ import annotations

import time
from src.core.logging import get_logger

logger = get_logger(__name__)

SLIPPAGE_WARNING_BPS = 15.0
ORDER_TIMEOUT_SECONDS = 90


def compute_slippage_bps(fill_price: float, expected_price: float, side: str) -> float:
    """
    Compute slippage in basis points.
    For buys: slippage = fill > expected (paid more)
    For sells: slippage = fill < expected (received less)
    Returns signed slippage (positive = bad, negative = favorable).
    """
    if expected_price <= 0:
        return 0.0
    if side == "buy":
        return (fill_price - expected_price) / expected_price * 10_000
    else:
        return (expected_price - fill_price) / expected_price * 10_000


def track_fill(
    order_id: str,
    expected_price: float,
    side: str = "buy",
) -> dict:
    """
    Track fill quality for a submitted order.
    Polls until filled or timeout.
    Returns {order_id, fill_price, slippage_bps, filled, elapsed_seconds}
    """
    from src.execution.broker import get_order_status, get_filled_price

    start = time.time()
    deadline = start + ORDER_TIMEOUT_SECONDS

    while time.time() < deadline:
        status = get_order_status(order_id)
        if not status:
            break
        if "filled" in status.lower():
            fill_price = get_filled_price(order_id)
            elapsed = time.time() - start
            if fill_price is not None:
                slippage = compute_slippage_bps(fill_price, expected_price, side)
                if slippage > SLIPPAGE_WARNING_BPS:
                    logger.warning(f"High slippage on {order_id}: {slippage:.1f}bps")
                return {
                    "order_id": order_id,
                    "fill_price": fill_price,
                    "slippage_bps": round(slippage, 2),
                    "filled": True,
                    "elapsed_seconds": round(elapsed, 1),
                }
            # fill_price not yet available from API — loop and retry
            time.sleep(2)
            continue
        if status in ("canceled", "expired", "rejected"):
            break
        time.sleep(2)

    elapsed = time.time() - start
    return {
        "order_id": order_id,
        "fill_price": None,
        "slippage_bps": None,
        "filled": False,
        "elapsed_seconds": round(elapsed, 1),
    }
