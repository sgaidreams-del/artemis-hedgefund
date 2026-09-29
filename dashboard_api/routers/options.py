"""Options flow / status endpoints — SPEC §11.1 Options panel."""
from __future__ import annotations

import datetime
import logging

from fastapi import APIRouter
from pydantic import BaseModel

from src.core.config import env
from src.core.db import conn

router = APIRouter(prefix="/api/options", tags=["options"])
log = logging.getLogger(__name__)


class EarningsExecuteBody(BaseModel):
    ticker: str
    earnings_date: str


def _bool_env(key: str) -> bool:
    return env(key, "false").lower() in ("1", "true", "yes")


@router.get("/status")
def status():
    return {
        "phase_a_flow": _bool_env("OPTIONS_FLOW_ENABLED"),
        "phase_b_execution": _bool_env("OPTIONS_EXECUTION_ENABLED"),
        "phase_c_earnings": _bool_env("OPTIONS_EARNINGS_ENABLED"),
        "phase_d_hedge": _bool_env("OPTIONS_HEDGE_ENABLED"),
    }


@router.get("/flow")
def flow(days: int = 14):
    try:
        cutoff = datetime.date.today() - datetime.timedelta(days=days)
        with conn() as c, c.cursor() as cur:
            cur.execute(
                "SELECT ticker, date, iv_rank, put_call_ratio, unusual_volume, signal "
                "FROM options_flow WHERE date >= %s ORDER BY date DESC",
                (cutoff,),
            )
            rows = cur.fetchall()

        if not rows:
            return {
                "signals": [],
                "empty_reason": f"No options flow data in the last {days} days.",
            }

        return {
            "signals": [
                {
                    "ticker": r[0],
                    "date": r[1].isoformat() if r[1] else None,
                    "iv_rank": float(r[2]) if r[2] is not None else None,
                    "put_call_ratio": float(r[3]) if r[3] is not None else None,
                    "unusual_volume": bool(r[4]),
                    "signal": r[5],
                }
                for r in rows
            ],
            "empty_reason": None,
        }
    except Exception as exc:
        log.exception("options flow failed")
        return {"error": str(exc), "signals": [], "empty_reason": str(exc)}


@router.get("/hedge-review")
def hedge_review():
    """Tail-risk hedge signal + concentration collar suggestions. Read-only — advisory only."""
    try:
        from src.execution.broker import get_account, get_positions
        from src.strategy.hedge import run_hedge_review

        account = get_account()
        portfolio_value = account["equity"] if account else 0.0
        positions = get_positions()
        return run_hedge_review(portfolio_value, positions)
    except Exception as exc:
        log.exception("hedge review failed")
        return {"error": str(exc), "tail_hedge": None, "collar_suggestions": []}


@router.get("/earnings-scan")
def earnings_scan():
    """Upcoming-earnings straddle signals. Read-only — never submits orders."""
    try:
        from src.strategy.earnings_options import scan_earnings_signals

        return {"signals": scan_earnings_signals()}
    except Exception as exc:
        log.exception("earnings scan failed")
        return {"error": str(exc), "signals": []}


@router.post("/earnings-scan/execute")
def earnings_scan_execute(body: EarningsExecuteBody):
    """Submit a pre-earnings straddle for one ticker. Real (paper) orders — human-initiated only."""
    try:
        from datetime import date as date_cls

        from src.execution.broker import get_account
        from src.strategy.earnings_options import execute_straddle

        account = get_account()
        portfolio_value = account["equity"] if account else 0.0

        earnings_date = date_cls.fromisoformat(body.earnings_date)
        return execute_straddle(body.ticker, earnings_date, portfolio_value)
    except Exception as exc:
        log.exception("earnings straddle execution failed")
        return {"error": str(exc), "call_order": None, "put_order": None, "total_premium": 0.0}


@router.get("/positions")
def positions():
    try:
        with conn() as c, c.cursor() as cur:
            cur.execute(
                "SELECT * FROM options_positions WHERE closed_at IS NULL "
                "ORDER BY opened_at DESC"
            )
            rows = cur.fetchall()
            col_names = [desc[0] for desc in cur.description]

        if not rows:
            return {
                "positions": [],
                "empty_reason": "No open options positions.",
            }

        def _serialise(v):
            if hasattr(v, "isoformat"):
                return v.isoformat()
            return v

        return {
            "positions": [
                {col: _serialise(val) for col, val in zip(col_names, row)}
                for row in rows
            ],
            "empty_reason": None,
        }
    except Exception as exc:
        log.exception("options positions failed")
        return {"error": str(exc), "positions": [], "empty_reason": str(exc)}
