"""Earnings options strategies (Phase C).

Two sub-strategies:
1. Pre-earnings IV expansion: buy ATM straddle when IV rank < 50th pct, 7-14 days before earnings.
   Rationale: IV typically expands into earnings even if direction is uncertain.
2. Post-earnings PEAD: directional call/put after earnings surprise direction is known.
   Rationale: post-earnings drift (PEAD) persists 5-20 days after announcement.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from ..core.db import conn
from ..data.options_flow import get_iv_rank
from ..execution.options import find_option, options_configured, submit_option_order

logger = logging.getLogger(__name__)


def upcoming_earnings(days_ahead: int = 14) -> list[dict]:
    """Query calendar_events for earnings in the next days_ahead days."""
    try:
        today = date.today()
        cutoff = today + timedelta(days=days_ahead)
        with conn() as c, c.cursor() as cur:
            cur.execute(
                """
                SELECT ticker, event_date
                FROM calendar_events
                WHERE event_type = 'earnings'
                  AND event_date BETWEEN %s AND %s
                  AND ticker IS NOT NULL
                ORDER BY event_date
                """,
                (today, cutoff),
            )
            rows = cur.fetchall()
        return [
            {
                "ticker": r[0],
                "earnings_date": r[1],
                "days_out": (r[1] - today).days,
            }
            for r in rows
        ]
    except Exception:
        logger.exception("upcoming_earnings failed")
        return []


def pre_earnings_straddle_signal(ticker: str, earnings_date: date) -> dict:
    """Return straddle/skip signal for a pre-earnings IV expansion play."""
    today = date.today()
    days_to_earnings = (earnings_date - today).days

    if not (7 <= days_to_earnings <= 14):
        return {
            "action": "skip",
            "reason": f"days_to_earnings={days_to_earnings} outside [7,14] entry window",
            "iv_rank": None,
            "days_to_earnings": days_to_earnings,
        }

    if not options_configured():
        return {
            "action": "skip",
            "reason": "options execution not configured",
            "iv_rank": None,
            "days_to_earnings": days_to_earnings,
        }

    iv_rank = get_iv_rank(ticker)

    if iv_rank is None:
        return {
            "action": "skip",
            "reason": "iv_rank unavailable",
            "iv_rank": None,
            "days_to_earnings": days_to_earnings,
        }

    if iv_rank >= 50.0:
        return {
            "action": "skip",
            "reason": f"iv_rank={iv_rank:.1f} >= 50 — IV already elevated, no expansion edge",
            "iv_rank": iv_rank,
            "days_to_earnings": days_to_earnings,
        }

    return {
        "action": "straddle",
        "reason": (
            f"iv_rank={iv_rank:.1f} < 50 with {days_to_earnings}d to earnings "
            "— IV expansion play valid"
        ),
        "iv_rank": iv_rank,
        "days_to_earnings": days_to_earnings,
    }


def post_earnings_pead_signal(ticker: str, earnings_surprise_pct: float) -> dict:
    """Return call/put/skip for a post-earnings PEAD directional play.

    Also checks that the current market regime is not strongly opposed to direction.
    """
    try:
        # Fetch most recent regime to avoid chasing against strong trends
        with conn() as c, c.cursor() as cur:
            cur.execute(
                "SELECT regime FROM regime_history ORDER BY date DESC LIMIT 1"
            )
            row = cur.fetchone()
        regime = row[0] if row else None
    except Exception:
        logger.exception("post_earnings_pead_signal: regime lookup failed")
        regime = None

    bear_regime = regime in ("bear_low_vol", "bear_high_vol") if regime else False
    bull_regime = regime in ("bull_low_vol", "bull_high_vol") if regime else False

    if earnings_surprise_pct > 2.0:
        if bear_regime:
            return {
                "action": "skip",
                "reason": f"positive surprise but bear regime ({regime}) opposes long call",
                "target_delta": 0.40,
            }
        return {
            "action": "call",
            "reason": f"surprise={earnings_surprise_pct:.1f}% > 2% — PEAD long call",
            "target_delta": 0.40,
        }

    if earnings_surprise_pct < -2.0:
        if bull_regime:
            return {
                "action": "skip",
                "reason": f"negative surprise but bull regime ({regime}) opposes long put",
                "target_delta": 0.40,
            }
        return {
            "action": "put",
            "reason": f"surprise={earnings_surprise_pct:.1f}% < -2% — PEAD long put",
            "target_delta": 0.40,
        }

    return {
        "action": "skip",
        "reason": f"surprise={earnings_surprise_pct:.1f}% within ±2% — no PEAD edge",
        "target_delta": 0.40,
    }


def execute_straddle(
    ticker: str, earnings_date: date, portfolio_value: float
) -> dict:
    """Buy ATM call and put expiring 1-2 days after earnings_date.

    Each leg sized at 0.5% of portfolio_value (total straddle ≤ 1%).
    """
    result: dict = {"call_order": None, "put_order": None, "total_premium": 0.0}

    # Expiry 1-2 days after earnings — fit it in the 0-7 day window for find_option
    days_to_earnings = (earnings_date - date.today()).days
    expiry_min = max(0, days_to_earnings + 1)
    expiry_max = days_to_earnings + 3

    leg_budget = portfolio_value * 0.005  # 0.5% per leg

    for option_type, key in (("call", "call_order"), ("put", "put_order")):
        try:
            contract = find_option(
                ticker,
                option_type,
                target_delta=0.50,  # ATM for straddle
                expiry_min_days=expiry_min,
                expiry_max_days=expiry_max,
            )
            if contract is None:
                logger.warning("execute_straddle: no %s contract found for %s", option_type, ticker)
                continue

            last_price = contract.get("lastPrice") or 0.0
            if last_price <= 0:
                logger.warning("execute_straddle: zero lastPrice for %s %s", ticker, option_type)
                continue

            # qty in contracts (100 shares each); floor to at least 1
            qty = max(1, int(leg_budget / (last_price * 100)))
            order = submit_option_order(
                symbol=contract["symbol"],
                qty=qty,
                side="buy",
                limit_price=round(last_price * 1.01, 2),  # 1% above last to ensure fill
                strategy_type="straddle",
            )
            result[key] = order
            if order is not None:
                result["total_premium"] += last_price * qty * 100
        except Exception:
            logger.exception(
                "execute_straddle leg failed",
                extra={"ticker": ticker, "leg": option_type},
            )

    return result


def scan_earnings_signals() -> list[dict]:
    """Scan upcoming earnings and return straddle signals. Never submits orders.

    Execution (execute_straddle) is a separate, explicitly human-triggered step —
    this function only reports what the strategy would do.
    """
    log_entries: list[dict] = []
    events = upcoming_earnings(days_ahead=14)

    for event in events:
        ticker = event["ticker"]
        earnings_date = event["earnings_date"]
        try:
            signal = pre_earnings_straddle_signal(ticker, earnings_date)
            log_entries.append({
                "ticker": ticker,
                "earnings_date": earnings_date.isoformat(),
                "signal": signal,
            })
        except Exception:
            logger.exception("scan_earnings_signals: error on ticker", extra={"ticker": ticker})

    return log_entries
