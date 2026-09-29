"""Portfolio hedging strategies (Phase D).

Two hedging mechanisms:
1. Tail-risk hedge: buy OTM SPY puts when the Burry/Taleb bear checklist (SPEC §6.4.1)
   score exceeds a threshold. Sized as 0.5-1% of portfolio equity.
2. Collar writing: suggest covered calls on positions > 10% of portfolio to reduce cost basis.
   Collars are advisory only until Phase 5 execution ships.
"""
from __future__ import annotations

import logging

from ..core.db import conn
from ..execution.options import find_option, submit_option_order

logger = logging.getLogger(__name__)


def bear_checklist_score(ticker: str) -> float:
    """Simplified SPEC §6.4.1 bear checklist. Returns a 0-10 score."""
    try:
        with conn() as c, c.cursor() as cur:
            cur.execute(
                """
                SELECT pe_ratio, dividend_yield, market_cap
                FROM fundamentals
                WHERE ticker = %s
                ORDER BY asof_date DESC
                LIMIT 1
                """,
                (ticker,),
            )
            fund_row = cur.fetchone()

            cur.execute(
                """
                SELECT feature_name, value
                FROM features_daily
                WHERE ticker = %s
                  AND feature_name IN ('momentum_20d', 'volatility_20d')
                ORDER BY date DESC
                LIMIT 2
                """,
                (ticker,),
            )
            feature_rows = cur.fetchall()

        if not fund_row:
            return 0.0

        pe_ratio = float(fund_row[0]) if fund_row[0] is not None else None
        div_yield = float(fund_row[1]) if fund_row[1] is not None else None
        market_cap = float(fund_row[2]) if fund_row[2] is not None else None

        features = {r[0]: float(r[1]) for r in feature_rows}
        momentum_20d = features.get("momentum_20d")
        volatility_20d = features.get("volatility_20d")

        score = 0.0
        if pe_ratio is not None and pe_ratio > 30:
            score += 2.0
        if momentum_20d is not None and momentum_20d < -0.05:
            score += 2.0
        if volatility_20d is not None and volatility_20d > 0.35:
            score += 2.0
        if div_yield is not None and div_yield == 0.0:
            score += 2.0
        if market_cap is not None and market_cap < 1e9:
            score += 2.0

        return score
    except Exception:
        logger.exception("bear_checklist_score failed", extra={"ticker": ticker})
        return 0.0


def portfolio_tail_risk_score(positions: list[dict]) -> float:
    """Weighted average bear_checklist_score across positions by market_value."""
    if not positions:
        return 0.0

    total_weight = 0.0
    weighted_sum = 0.0

    for pos in positions:
        mv = float(pos.get("market_value") or 0.0)
        if mv <= 0:
            continue
        ticker = pos.get("ticker") or pos.get("symbol", "")
        if not ticker:
            continue
        score = bear_checklist_score(ticker)
        weighted_sum += score * mv
        total_weight += mv

    if total_weight <= 0:
        return 0.0
    return weighted_sum / total_weight


def tail_hedge_signal(portfolio_value: float, positions: list[dict]) -> dict:
    """Recommend a tail-risk SPY put hedge based on portfolio bear score."""
    score = portfolio_tail_risk_score(positions)

    if score > 6.0:
        size_pct = 1.0
        action = "hedge"
        reason = f"Bear checklist score {score:.1f} > 6 — 1% OTM SPY put hedge recommended"
    elif score > 4.0:
        size_pct = 0.5
        action = "hedge"
        reason = f"Bear checklist score {score:.1f} > 4 — 0.5% OTM SPY put hedge recommended"
    else:
        size_pct = 0.0
        action = "no_hedge"
        reason = f"Bear checklist score {score:.1f} ≤ 4 — portfolio tail risk acceptable"

    return {
        "action": action,
        "score": score,
        "recommended_size_pct": size_pct,
        "reason": reason,
    }


def collar_suggestions(positions: list[dict], portfolio_value: float) -> list[dict]:
    """Suggest covered call collars for concentrated positions (>10% of portfolio).

    Advisory only — no orders submitted.
    """
    suggestions: list[dict] = []
    if portfolio_value <= 0:
        return suggestions

    for pos in positions:
        mv = float(pos.get("market_value") or 0.0)
        weight_pct = mv / portfolio_value * 100.0
        if weight_pct <= 10.0:
            continue

        ticker = pos.get("ticker") or pos.get("symbol", "")
        if not ticker:
            continue

        # Find a 25-delta call 30-45 DTE as the collar leg
        call_contract = None
        try:
            call_contract = find_option(
                ticker,
                "call",
                target_delta=0.25,
                expiry_min_days=30,
                expiry_max_days=45,
            )
        except Exception:
            logger.exception("collar_suggestions: find_option failed", extra={"ticker": ticker})

        suggested_strike = call_contract["strike"] if call_contract else None
        strike_info = f" at strike {suggested_strike:.2f}" if suggested_strike else ""

        suggestions.append(
            {
                "ticker": ticker,
                "weight_pct": round(weight_pct, 2),
                "suggested_strike": suggested_strike,
                "rationale": (
                    f"{ticker} is {weight_pct:.1f}% of portfolio — concentration risk. "
                    f"Sell 25-delta call 30-45 DTE{strike_info} to collect premium and "
                    "reduce cost basis. Advisory only."
                ),
            }
        )
        logger.info(
            "collar suggestion: %s %.1f%% weight, strike=%s", ticker, weight_pct, suggested_strike
        )

    return suggestions


def run_hedge_review(portfolio_value: float, positions: list[dict]) -> dict:
    """Run full hedge review: tail-risk signal + collar suggestions."""
    try:
        tail_signal = tail_hedge_signal(portfolio_value, positions)
        collars = collar_suggestions(positions, portfolio_value)

        # If a hedge is recommended, also find the SPY put contract details
        spy_put_contract: dict | None = None
        if tail_signal["action"] == "hedge":
            try:
                spy_put_contract = find_option(
                    "SPY",
                    "put",
                    target_delta=0.25,
                    expiry_min_days=40,
                    expiry_max_days=50,
                )
            except Exception:
                logger.exception("run_hedge_review: SPY put lookup failed")

        return {
            "tail_hedge": tail_signal,
            "spy_put_contract": spy_put_contract,
            "collar_suggestions": collars,
            "portfolio_value": portfolio_value,
            "positions_reviewed": len(positions),
        }
    except Exception:
        logger.exception("run_hedge_review failed")
        return {
            "tail_hedge": {"action": "no_hedge", "score": 0.0, "recommended_size_pct": 0.0, "reason": "error"},
            "spy_put_contract": None,
            "collar_suggestions": [],
            "portfolio_value": portfolio_value,
            "positions_reviewed": 0,
        }
