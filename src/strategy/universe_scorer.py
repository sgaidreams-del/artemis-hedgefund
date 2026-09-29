"""Score the full universe of tickers using the ensemble combiner."""
from __future__ import annotations

import json
import math
from datetime import date

from src.core.db import conn
from src.core.logging import get_logger
from src.strategy.ensemble.combiner import combine_signals_batch
from src.strategy.ensemble.weights import load_weights

log = get_logger("universe_scorer")

_CONFIDENCE_FLOOR = 0.1

_REGIME_ID_BY_LABEL = {
    "Bull/Low-Vol": 0,
    "Bull/High-Vol": 1,
    "Bear/Low-Vol": 2,
    "Bear/High-Vol": 3,
    "Sideways": 4,
}


def _softmax(scores: list[float]) -> list[float]:
    """Numerically stable softmax."""
    if not scores:
        return []
    max_val = max(scores)
    exps = [math.exp(s - max_val) for s in scores]
    total = sum(exps)
    return [e / total for e in exps]


def score_universe(
    tickers: list[str],
    date: str,
    regime: str,
    rl_decisions: dict,
) -> list[dict]:
    """Score every ticker and return the filtered, softmax-weighted universe.

    Parameters
    ----------
    tickers:
        Universe of ticker symbols to evaluate.
    date:
        ISO date string (YYYY-MM-DD) for which to retrieve signals.
    regime:
        Market regime string used to adjust weights (e.g. 'Bull/Low-Vol').
    rl_decisions:
        Dict produced by the RL agent; expected to contain 'equity_alloc'
        (a float multiplier, typically in [0, 1]).

    Returns
    -------
    list[dict]
        Each element: {'ticker': str, 'score': float, 'target_weight': float},
        sorted descending by score. Only includes tickers with score > 0.1.
    """
    equity_alloc = float(rl_decisions.get("equity_alloc", 1.0))

    # Load weights once outside the per-ticker loop (batch helper does this internally)
    raw_scores = combine_signals_batch(tickers, date, regime)

    # Apply RL tilt and filter by confidence floor
    candidates: list[dict] = []
    for ticker, raw_score in raw_scores.items():
        if raw_score is None:
            continue
        score = raw_score * equity_alloc
        if score > _CONFIDENCE_FLOOR:
            candidates.append({"ticker": ticker, "score": score})

    if not candidates:
        log.info("score_universe: no tickers passed confidence floor on %s", date)
        return []

    # Sort descending by score
    candidates.sort(key=lambda x: x["score"], reverse=True)

    # Compute softmax target weights
    score_values = [c["score"] for c in candidates]
    weights = _softmax(score_values)

    result = []
    for candidate, target_weight in zip(candidates, weights):
        result.append(
            {
                "ticker": candidate["ticker"],
                "score": candidate["score"],
                "target_weight": target_weight,
            }
        )

    log.info(
        "score_universe: date=%s regime=%s tickers_in=%d tickers_out=%d",
        date,
        regime,
        len(tickers),
        len(result),
    )
    return result


def _build_portfolio_state(regime_label: str):
    """Build a PortfolioState from current account + recent drawdown for the RL agent.

    avg_momentum/avg_vol default to 0.0 — no cheap aggregate source for these
    across current holdings yet. Safe because get_portfolio_decisions() already
    falls back to equal-weight on any downstream error.
    """
    from src.execution.broker import get_account
    from src.strategy.rl.environment import PortfolioState

    account = get_account()
    equity = account["equity"] if account else 0.0
    cash = account["cash"] if account else 0.0
    equity_alloc = (equity - cash) / equity if account and equity > 0 else 0.6

    drawdown = 0.0
    with conn() as c, c.cursor() as cur:
        cur.execute("SELECT drawdown FROM portfolio_snapshots ORDER BY date DESC LIMIT 1")
        row = cur.fetchone()
        if row and row[0] is not None:
            drawdown = float(row[0])

    return PortfolioState(
        equity_alloc=equity_alloc,
        avg_momentum=0.0,
        avg_vol=0.0,
        current_drawdown=drawdown,
        regime_id=_REGIME_ID_BY_LABEL.get(regime_label, 4),
    )


def run_ensemble_pipeline(tickers: list[str]) -> dict:
    """Daily entry point: score the universe and upsert today's ensemble_scores.

    Reads the regime written earlier in the day by run_regime_pipeline() from
    regime_history rather than threading it through in-memory — keeps this job
    independently runnable/idempotent like every other pipeline stage.
    """
    from src.strategy.rl.finrl_agent import get_portfolio_decisions

    today = date.today().isoformat()

    with conn() as c, c.cursor() as cur:
        cur.execute("SELECT regime FROM regime_history WHERE date = %s", (today,))
        row = cur.fetchone()
    regime_label = row[0] if row else "Sideways"

    portfolio_state = _build_portfolio_state(regime_label)
    rl_decisions = get_portfolio_decisions(portfolio_state)

    scored = score_universe(tickers, today, regime_label, rl_decisions)

    with conn() as c, c.cursor() as cur:
        for item in scored:
            cur.execute(
                """
                INSERT INTO ensemble_scores (ticker, date, final_score, target_weight, regime, component_scores)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (ticker, date) DO UPDATE
                  SET final_score=EXCLUDED.final_score,
                      target_weight=EXCLUDED.target_weight,
                      regime=EXCLUDED.regime,
                      component_scores=EXCLUDED.component_scores
                """,
                (item["ticker"], today, item["score"], item["target_weight"], regime_label,
                 json.dumps(rl_decisions)),
            )
        c.commit()

    log.info("run_ensemble_pipeline: date=%s regime=%s scored=%d", today, regime_label, len(scored))
    return {"tickers_scored": len(scored), "regime": regime_label}
