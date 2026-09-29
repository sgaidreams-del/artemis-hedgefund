"""Trade journaling — writes completed trades to the DB."""
from __future__ import annotations

import json
import uuid
from src.core.db import conn
from src.core.logging import get_logger

logger = get_logger(__name__)


def generate_trade_id() -> str:
    return str(uuid.uuid4())


def log_trade(
    ticker: str,
    side: str,
    qty: int,
    order_type: str,
    limit_price: float | None,
    fill_price: float | None,
    slippage_bps: float | None,
    signals: dict | None = None,
    risk_snapshot: dict | None = None,
    rationale: str | None = None,
    trade_id: str | None = None,
) -> str:
    """
    Write a completed trade to the trades table.
    Returns the trade_id.
    """
    trade_id = trade_id or generate_trade_id()

    with conn() as c, c.cursor() as cur:
        cur.execute(
            """
            INSERT INTO trades
            (trade_id, timestamp, ticker, side, quantity, order_type,
             limit_price, fill_price, slippage_bps, signals, risk_snapshot, rationale)
            VALUES (%s, NOW(), %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
            ON CONFLICT (trade_id) DO NOTHING
            """,
            (
                trade_id,
                ticker, side, qty, order_type,
                limit_price, fill_price, slippage_bps,
                json.dumps(signals or {}),
                json.dumps(risk_snapshot or {}),
                rationale,
            )
        )

    logger.info(f"Trade logged: {side} {qty}x{ticker} @ {fill_price} [{trade_id[:8]}]")
    return trade_id


def get_recent_trades(ticker: str = None, n: int = 50) -> list[dict]:
    """Get recent trades, optionally filtered by ticker."""
    with conn() as c, c.cursor() as cur:
        if ticker:
            cur.execute(
                """
                SELECT trade_id, timestamp, ticker, side, quantity, order_type,
                       limit_price, fill_price, slippage_bps, rationale
                FROM trades WHERE ticker = %s
                ORDER BY timestamp DESC LIMIT %s
                """,
                (ticker, n)
            )
        else:
            cur.execute(
                """
                SELECT trade_id, timestamp, ticker, side, quantity, order_type,
                       limit_price, fill_price, slippage_bps, rationale
                FROM trades ORDER BY timestamp DESC LIMIT %s
                """,
                (n,)
            )
        rows = cur.fetchall()

    cols = ["trade_id", "timestamp", "ticker", "side", "quantity", "order_type",
            "limit_price", "fill_price", "slippage_bps", "rationale"]
    return [dict(zip(cols, row)) for row in rows]
