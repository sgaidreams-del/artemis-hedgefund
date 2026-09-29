"""Portfolio overview + history. SPEC §11.1 Portfolio Overview page."""
from __future__ import annotations

from fastapi import APIRouter

from src.core.db import conn
from .. import alpaca_client

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("/overview")
def overview():
    account = alpaca_client.get_account()
    positions = alpaca_client.get_positions()
    if account is None:
        return {
            "connected": False,
            "message": "Alpaca not configured — add ALPACA_API_KEY/SECRET to .env",
            "account": None,
            "positions": [],
        }
    return {"connected": True, "account": account, "positions": positions}


@router.get("/history")
def history(period: str = "1M", timeframe: str = "1D"):
    """Prefers our own enriched portfolio_snapshots once Phase 5+ populates it;
    falls back to Alpaca's own ledger, which is real and available from day one.
    """
    with conn() as c, c.cursor() as cur:
        cur.execute(
            "SELECT date, total_value, daily_return, cumulative_return, drawdown, regime "
            "FROM portfolio_snapshots ORDER BY date ASC"
        )
        rows = cur.fetchall()
    if rows:
        return {
            "source": "internal_snapshots",
            "points": [
                {
                    "date": r[0].isoformat(),
                    "total_value": float(r[1]) if r[1] is not None else None,
                    "daily_return": float(r[2]) if r[2] is not None else None,
                    "cumulative_return": float(r[3]) if r[3] is not None else None,
                    "drawdown": float(r[4]) if r[4] is not None else None,
                    "regime": r[5],
                }
                for r in rows
            ],
        }
    alpaca_points = alpaca_client.get_portfolio_history(period=period, timeframe=timeframe)
    return {"source": "alpaca_ledger" if alpaca_points else "none", "points": alpaca_points}
