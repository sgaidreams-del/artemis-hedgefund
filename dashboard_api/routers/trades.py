"""Trade history — SPEC §11.1 Trade Log page. Each row carries full rationale."""
from __future__ import annotations

from fastapi import APIRouter

from src.core.db import conn

router = APIRouter(prefix="/api/trades", tags=["trades"])


@router.get("")
def list_trades(limit: int = 100):
    with conn() as c, c.cursor() as cur:
        cur.execute(
            """
            SELECT trade_id, timestamp, ticker, side, quantity, order_type,
                   limit_price, fill_price, slippage_bps, signals, risk_snapshot, rationale
            FROM trades
            ORDER BY timestamp DESC
            LIMIT %s
            """,
            (limit,),
        )
        rows = cur.fetchall()
    return {
        "trades": [
            {
                "trade_id": r[0],
                "timestamp": r[1].isoformat(),
                "ticker": r[2],
                "side": r[3],
                "quantity": r[4],
                "order_type": r[5],
                "limit_price": float(r[6]) if r[6] is not None else None,
                "fill_price": float(r[7]) if r[7] is not None else None,
                "slippage_bps": float(r[8]) if r[8] is not None else None,
                "signals": r[9],
                "risk_snapshot": r[10],
                "rationale": r[11],
            }
            for r in rows
        ],
        "empty_reason": None if rows else "No trades yet — execution layer (Phase 5) hasn't shipped, "
                                            "and the system hasn't placed any orders.",
    }
