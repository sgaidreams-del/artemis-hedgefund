"""
Alpaca broker wrapper for equity trading.
All functions are stateless and safe to call from any context.
No market orders — limit only.
"""
from __future__ import annotations

import os
from functools import lru_cache
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOrdersRequest, LimitOrderRequest
from alpaca.trading.enums import OrderSide, QueryOrderStatus, TimeInForce
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest
from src.core.logging import get_logger

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def _trading_client() -> TradingClient | None:
    """Cached TradingClient. Returns None if credentials not set."""
    key = os.environ.get("ALPACA_API_KEY")
    secret = os.environ.get("ALPACA_API_SECRET")
    base_url = os.environ.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

    if not key or not secret:
        logger.warning("Alpaca credentials not set — broker unavailable")
        return None

    paper = "paper" in base_url
    return TradingClient(api_key=key, secret_key=secret, paper=paper)


def is_market_open() -> bool | None:
    """Whether the US equity market is currently open, per Alpaca's clock.

    Returns None if the clock can't be read — callers must treat None as
    'unknown' and fail closed, not assume open.
    """
    client = _trading_client()
    if client is None:
        return None
    try:
        return bool(client.get_clock().is_open)
    except Exception as e:
        logger.error(f"is_market_open failed: {e}")
        return None


def get_account() -> dict | None:
    """Get account info. Returns None on failure."""
    client = _trading_client()
    if client is None:
        return None
    try:
        account = client.get_account()
        return {
            "equity": float(account.equity),
            "cash": float(account.cash),
            "buying_power": float(account.buying_power),
            "status": account.status.value if hasattr(account.status, 'value') else str(account.status),
        }
    except Exception as e:
        logger.error(f"get_account failed: {e}")
        return None


def get_positions() -> list[dict]:
    """Get all open positions. Returns empty list on failure."""
    client = _trading_client()
    if client is None:
        return []
    try:
        positions = client.get_all_positions()
        return [
            {
                "ticker": p.symbol,
                "qty": int(p.qty),
                "avg_entry_price": float(p.avg_entry_price),
                "current_price": float(p.current_price),
                "market_value": float(p.market_value),
                "unrealized_pl": float(p.unrealized_pl),
            }
            for p in positions
        ]
    except Exception as e:
        logger.error(f"get_positions failed: {e}")
        return []


def get_latest_quote(ticker: str) -> dict | None:
    """Latest mid-price plus the quote's age in seconds (for staleness checks).

    age_seconds uses the quote's own timestamp from Alpaca, not local clock
    skew — IEX free-tier quotes can lag real-time.
    """
    key = os.environ.get("ALPACA_API_KEY")
    secret = os.environ.get("ALPACA_API_SECRET")
    if not key or not secret:
        return None
    try:
        from datetime import datetime, timezone

        data_client = StockHistoricalDataClient(api_key=key, secret_key=secret)
        req = StockLatestQuoteRequest(symbol_or_symbols=[ticker])
        quotes = data_client.get_stock_latest_quote(req)
        q = quotes[ticker]
        age_seconds = (datetime.now(timezone.utc) - q.timestamp).total_seconds()
        return {"price": float((q.bid_price + q.ask_price) / 2), "age_seconds": age_seconds}
    except Exception as e:
        logger.warning(f"get_latest_quote failed for {ticker}: {e}")
        return None


def get_latest_price(ticker: str) -> float | None:
    """Get latest mid-price for a ticker."""
    quote = get_latest_quote(ticker)
    return quote["price"] if quote else None


def submit_limit_order(
    ticker: str,
    qty: int,
    side: str,  # "buy" | "sell"
    limit_price: float,
    time_in_force: str = "day",
) -> dict | None:
    """
    Submit a limit order. Returns order dict on success, None on failure.
    NEVER submits market orders.
    """
    if qty <= 0:
        logger.warning(f"Attempted to submit zero/negative qty for {ticker}")
        return None

    client = _trading_client()
    if client is None:
        return None

    order_side = OrderSide.BUY if side == "buy" else OrderSide.SELL
    tif = TimeInForce.DAY if time_in_force == "day" else TimeInForce.IOC

    try:
        req = LimitOrderRequest(
            symbol=ticker,
            qty=qty,
            side=order_side,
            time_in_force=tif,
            limit_price=round(limit_price, 2),
        )
        order = client.submit_order(req)
        logger.info(f"Order submitted: {side} {qty}x{ticker} @ {limit_price:.2f} [{order.id}]")
        return {
            "order_id": str(order.id),
            "ticker": ticker,
            "side": side,
            "qty": qty,
            "limit_price": limit_price,
            "status": str(order.status),
        }
    except Exception as e:
        logger.error(f"submit_limit_order failed for {ticker}: {e}")
        return None


def cancel_order(order_id: str) -> bool:
    """Cancel an open order. Returns True on success."""
    client = _trading_client()
    if client is None:
        return False
    try:
        client.cancel_order_by_id(order_id)
        return True
    except Exception as e:
        logger.error(f"cancel_order {order_id} failed: {e}")
        return False


def get_open_orders() -> list[dict]:
    """Get all currently-open (resting) orders. Returns empty list on failure."""
    client = _trading_client()
    if client is None:
        return []
    try:
        orders = client.get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN))
        return [
            {"order_id": str(o.id), "ticker": o.symbol, "side": str(o.side), "qty": int(o.qty or 0)}
            for o in orders
        ]
    except Exception as e:
        logger.error(f"get_open_orders failed: {e}")
        return []


def cancel_all_orders() -> int:
    """Cancel every open order. Returns the count of orders the broker attempted to cancel.

    Used by the kill switch — engaging it should stop resting orders from
    filling, not just block new submissions.
    """
    client = _trading_client()
    if client is None:
        return 0
    try:
        responses = client.cancel_orders()
        logger.warning(f"cancel_all_orders: cancelled {len(responses)} resting order(s)")
        return len(responses)
    except Exception as e:
        logger.error(f"cancel_all_orders failed: {e}")
        return 0


def flatten_all(confirm: bool = False) -> list[dict]:
    """Liquidate every open position at market via Alpaca's close-all-positions call.

    Manual-only escape hatch — never called automatically by any halt or kill
    switch in this system. Requires confirm=True so it can't fire by accident
    from a default-argument call.
    """
    if not confirm:
        logger.warning("flatten_all called without confirm=True — refusing")
        return []
    client = _trading_client()
    if client is None:
        return []
    try:
        responses = client.close_all_positions(cancel_orders=True)
        logger.warning(f"flatten_all: closed {len(responses)} position(s)")
        return [{"symbol": r.symbol, "status": str(r.status)} for r in responses]
    except Exception as e:
        logger.error(f"flatten_all failed: {e}")
        return []


def get_order_status(order_id: str) -> str | None:
    """Get current status of an order. Returns status string or None."""
    client = _trading_client()
    if client is None:
        return None
    try:
        order = client.get_order_by_id(order_id)
        return str(order.status)
    except Exception as e:
        logger.error(f"get_order_status {order_id} failed: {e}")
        return None


def get_filled_price(order_id: str) -> float | None:
    """Get fill price of a filled order."""
    client = _trading_client()
    if client is None:
        return None
    try:
        order = client.get_order_by_id(order_id)
        if order.filled_avg_price:
            return float(order.filled_avg_price)
        return None
    except Exception as e:
        logger.error(f"get_filled_price {order_id} failed: {e}")
        return None
