"""Simulator API — portfolio state, positions, trades, snapshots, weekly reports, toggle."""
from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter(prefix="/api/sim", tags=["simulator"])
log = logging.getLogger(__name__)


@router.get("/status")
def sim_status():
    """Current sim portfolio: cash, equity, P/L, enabled flag."""
    try:
        from src.simulation.engine import _ensure_config, _get_prices
        from src.core.db import conn

        with conn() as c, c.cursor() as cur:
            _ensure_config(cur)
            cur.execute("SELECT cash, starting_capital, enabled FROM sim_config WHERE id = 1")
            row = cur.fetchone()
            if row is None:
                return {"enabled": False, "cash": 100000.0, "starting_capital": 100000.0,
                        "positions_value": 0.0, "total_value": 100000.0,
                        "total_pnl": 0.0, "total_return_pct": 0.0}
            cash, starting_capital, enabled = float(row[0]), float(row[1]), bool(row[2])

            cur.execute("SELECT ticker, qty FROM sim_positions")
            open_pos = {r[0]: int(r[1]) for r in cur.fetchall()}

        prices = _get_prices(set(open_pos.keys()))
        positions_value = sum(open_pos[t] * prices.get(t, 0.0) for t in open_pos)
        total_value = cash + positions_value
        total_pnl = total_value - starting_capital
        total_return_pct = (total_pnl / starting_capital * 100.0) if starting_capital > 0 else 0.0

        return {
            "enabled": enabled,
            "starting_capital": starting_capital,
            "cash": round(cash, 2),
            "positions_value": round(positions_value, 2),
            "total_value": round(total_value, 2),
            "total_pnl": round(total_pnl, 2),
            "total_return_pct": round(total_return_pct, 4),
        }
    except Exception as exc:
        log.exception("sim_status failed")
        return {"error": str(exc)}


@router.get("/positions")
def sim_positions():
    """Open sim positions with unrealized P/L."""
    try:
        from src.simulation.engine import _get_prices
        from src.core.db import conn

        with conn() as c, c.cursor() as cur:
            cur.execute(
                "SELECT ticker, qty, avg_cost, cost_basis, first_entry, last_updated "
                "FROM sim_positions ORDER BY ticker"
            )
            rows = cur.fetchall()

        prices = _get_prices({r[0] for r in rows})
        result = []
        for ticker, qty, avg_cost, cost_basis, first_entry, last_updated in rows:
            current_price = prices.get(ticker, float(avg_cost))
            market_value = int(qty) * current_price
            unrealized_pnl = market_value - float(cost_basis)
            unrealized_pct = (unrealized_pnl / float(cost_basis) * 100.0) if cost_basis else 0.0
            result.append({
                "ticker": ticker,
                "qty": int(qty),
                "avg_cost": round(float(avg_cost), 4),
                "cost_basis": round(float(cost_basis), 2),
                "current_price": round(current_price, 4),
                "market_value": round(market_value, 2),
                "unrealized_pnl": round(unrealized_pnl, 2),
                "unrealized_pct": round(unrealized_pct, 4),
                "first_entry": first_entry.isoformat(),
                "last_updated": last_updated.isoformat(),
            })
        return {"positions": result}
    except Exception as exc:
        log.exception("sim_positions failed")
        return {"positions": [], "error": str(exc)}


@router.get("/trades")
def sim_trades(limit: int = Query(default=100, le=500)):
    """Recent simulated trades (buys and sells)."""
    try:
        from src.core.db import conn
        with conn() as c, c.cursor() as cur:
            cur.execute(
                "SELECT date, ticker, side, qty, price, notional, realized_pnl, "
                "target_weight, created_at FROM sim_trades ORDER BY created_at DESC LIMIT %s",
                (limit,),
            )
            rows = cur.fetchall()
        return {"trades": [
            {
                "date": r[0].isoformat(),
                "ticker": r[1],
                "side": r[2],
                "qty": int(r[3]),
                "price": float(r[4]),
                "notional": float(r[5]),
                "realized_pnl": float(r[6]) if r[6] is not None else None,
                "target_weight": float(r[7]) if r[7] is not None else None,
                "created_at": r[8].isoformat(),
            }
            for r in rows
        ]}
    except Exception as exc:
        log.exception("sim_trades failed")
        return {"trades": [], "error": str(exc)}


@router.get("/snapshots")
def sim_snapshots(days: int = Query(default=90, le=365)):
    """Daily equity snapshots (chronological) for charting."""
    try:
        from src.core.db import conn
        with conn() as c, c.cursor() as cur:
            cur.execute(
                "SELECT date, cash, positions_value, total_value, daily_return, "
                "cumulative_return, drawdown, open_positions "
                "FROM sim_snapshots ORDER BY date DESC LIMIT %s",
                (days,),
            )
            rows = cur.fetchall()
        return {"snapshots": [
            {
                "date": r[0].isoformat(),
                "cash": float(r[1]),
                "positions_value": float(r[2]),
                "total_value": float(r[3]),
                "daily_return": float(r[4]) if r[4] is not None else None,
                "cumulative_return": float(r[5]) if r[5] is not None else None,
                "drawdown": float(r[6]) if r[6] is not None else None,
                "open_positions": int(r[7]) if r[7] is not None else 0,
            }
            for r in reversed(rows)
        ]}
    except Exception as exc:
        log.exception("sim_snapshots failed")
        return {"snapshots": [], "error": str(exc)}


@router.get("/reports")
def sim_reports():
    """Weekly performance reports (most recent first)."""
    try:
        from src.core.db import conn
        with conn() as c, c.cursor() as cur:
            cur.execute(
                "SELECT week_ending, starting_value, ending_value, weekly_return_pct, "
                "total_return_pct, max_drawdown_pct, sharpe_weekly, total_trades, "
                "winning_trades, losing_trades, win_rate_pct, avg_win, avg_loss, "
                "profit_factor, gross_profit, gross_loss "
                "FROM sim_weekly_reports ORDER BY week_ending DESC LIMIT 52"
            )
            rows = cur.fetchall()
        keys = [
            "week_ending", "starting_value", "ending_value", "weekly_return_pct",
            "total_return_pct", "max_drawdown_pct", "sharpe_weekly", "total_trades",
            "winning_trades", "losing_trades", "win_rate_pct", "avg_win", "avg_loss",
            "profit_factor", "gross_profit", "gross_loss",
        ]
        return {"reports": [
            {k: (v.isoformat() if hasattr(v, "isoformat") else
                 (float(v) if v is not None else None))
             for k, v in zip(keys, r)}
            for r in rows
        ]}
    except Exception as exc:
        log.exception("sim_reports failed")
        return {"reports": [], "error": str(exc)}


class ToggleBody(BaseModel):
    enabled: bool


@router.post("/toggle")
def sim_toggle(body: ToggleBody):
    """Enable or disable the trade simulator."""
    try:
        from src.simulation.engine import set_sim_enabled
        set_sim_enabled(body.enabled)
        return {"enabled": body.enabled, "status": "ok"}
    except Exception as exc:
        log.exception("sim_toggle failed")
        return {"error": str(exc)}


@router.post("/reset")
def sim_reset():
    """Reset to $100K, clearing all positions/trades/snapshots."""
    try:
        from src.simulation.engine import reset_sim
        return reset_sim()
    except Exception as exc:
        log.exception("sim_reset failed")
        return {"error": str(exc)}


@router.post("/run")
def sim_run():
    """Manually trigger one sim step right now (same logic as the daily pipeline job)."""
    try:
        from src.simulation.engine import run_sim_step
        return run_sim_step()
    except Exception as exc:
        log.exception("sim_run failed")
        return {"error": str(exc)}


@router.post("/generate-report")
def generate_report():
    """Manually regenerate this week's report."""
    try:
        from src.simulation.reports import generate_weekly_report
        return generate_weekly_report()
    except Exception as exc:
        log.exception("generate_report failed")
        return {"error": str(exc)}
