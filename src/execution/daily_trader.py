"""Daily trade decision orchestrator.

Turns today's ensemble_scores (target weights, written by
strategy.universe_scorer.run_ensemble_pipeline) into rebalance orders,
gates them through risk limits, and routes them through the broker.

NOT wired into run_pipeline.py's automatic JOBS list. Call
run_daily_rebalance() explicitly — with dry_run=True first — until the
system has been observed long enough to trust running unattended.
"""
from __future__ import annotations

from datetime import date

from dashboard_api.routers.kill_switch import engage, is_paused
from src.core.db import conn
from src.core.logging import get_logger, log_activity
from src.execution.broker import get_account, get_latest_price, get_positions
from src.execution.journal import log_trade
from src.execution.monitor import compute_slippage_bps
from src.execution.order_router import route_order
from src.risk.correlation import compute_portfolio_correlation
from src.risk.limits import (
    check_cash_floor,
    check_consecutive_loss_halt,
    check_daily_loss_halt,
    check_exposure_limits,
    check_position_limit,
    check_trailing_drawdown_halt,
)
from src.risk.position_sizer import compute_max_shares
from src.risk.pretrade import validate_risk_config
from src.risk.rebalancer import compute_rebalance_orders
from src.risk.reconciliation import reconcile_options
from src.strategy.memory.trade_memory import log_decision

log = get_logger("daily_trader")


def _get_vol_60d(ticker: str) -> float:
    """Most recent vol_20d from features_daily as a vol proxy.

    Conservative default (20%) when no feature exists yet — lands in
    volatility_tier_cap's middle tier rather than the most permissive one.
    """
    with conn() as c, c.cursor() as cur:
        cur.execute(
            """
            SELECT value FROM features_daily
            WHERE ticker = %s AND feature_name = 'vol_20d'
            ORDER BY date DESC LIMIT 1
            """,
            (ticker,),
        )
        row = cur.fetchone()
    return float(row[0]) if row and row[0] is not None else 0.20


def _today_target_weights() -> tuple[dict[str, float], str]:
    # Use today's scores if the pipeline already ran today; otherwise the most
    # recent prior day's scores. The pipeline runs at 5pm, the trader at 9:35am
    # the next morning, so "today" will usually mean yesterday's pipeline run.
    today = date.today().isoformat()
    with conn() as c, c.cursor() as cur:
        cur.execute(
            """
            SELECT ticker, target_weight, regime
            FROM ensemble_scores
            WHERE date = (SELECT MAX(date) FROM ensemble_scores WHERE date <= %s)
            """,
            (today,),
        )
        rows = cur.fetchall()
    weights = {ticker: float(w) for ticker, w, _ in rows if w is not None}
    regime = rows[0][2] if rows else "unknown"
    return weights, regime


def run_daily_rebalance(dry_run: bool = True) -> dict:
    """Compute today's rebalance orders and optionally submit them.

    dry_run=True (default): compute and log decisions, do NOT submit to the
    broker. Pass dry_run=False explicitly to place real (paper-account) orders.
    """
    # Crash loudly if any risk limit is missing/zeroed/absurd — never trade
    # against an unvalidated config. Runs even for dry_run so previews surface
    # config problems early.
    validate_risk_config()

    if is_paused():
        log.info("run_daily_rebalance: kill switch active, skipping")
        return {"status": "paused", "orders": []}

    account = get_account()
    if account is None:
        log.warning("run_daily_rebalance: broker not connected")
        return {"status": "no_account", "orders": []}

    portfolio_value = account["equity"]
    held = get_positions()

    for halt_name, halt_fn in (
        ("daily_loss_halt", lambda: check_daily_loss_halt(portfolio_value)),
        ("trailing_drawdown_halt", lambda: check_trailing_drawdown_halt(portfolio_value)),
        ("consecutive_loss_halt", check_consecutive_loss_halt),
        ("cash_floor", lambda: check_cash_floor(account)),
        ("exposure_halt", lambda: check_exposure_limits(held, account)),
    ):
        if halt_fn():
            reason = f"{halt_name} breached at equity={portfolio_value:.2f}"
            log.warning(f"run_daily_rebalance: {reason} — freezing")
            engage(reason)
            return {"status": "halt", "halt": halt_name, "orders": []}

    # Reconciliation: a qty mismatch engages the kill switch on its own (see
    # reconcile_options); any finding at all means the book isn't trustworthy
    # enough to rebalance against this cycle, halt or not.
    findings = reconcile_options()
    if findings:
        log.warning(f"run_daily_rebalance: reconciliation mismatch, skipping — {findings}")
        return {"status": "reconciliation_mismatch", "findings": findings, "orders": []}

    target_weights, regime = _today_target_weights()
    if not target_weights:
        log.info("run_daily_rebalance: no ensemble_scores for today")
        return {"status": "no_scores", "orders": []}

    current = {
        p["ticker"]: {"qty": p["qty"], "price": p["current_price"], "market_value": p["market_value"]}
        for p in held
    }

    # compute_rebalance_orders needs a price entry for every target-weight
    # ticker, even ones not currently held, or it can't size a new position.
    for ticker in target_weights:
        if ticker not in current:
            price = get_latest_price(ticker)
            if price:
                current[ticker] = {"qty": 0, "price": price, "market_value": 0.0}

    portfolio_corr = compute_portfolio_correlation(list(current.keys())) if len(current) >= 2 else 0.0

    max_shares_map = {}
    for ticker, pos in current.items():
        price = pos.get("price") or 0.0
        if price <= 0:
            continue
        max_shares_map[ticker] = compute_max_shares(
            ticker, portfolio_value, price, _get_vol_60d(ticker), portfolio_corr
        )

    orders = compute_rebalance_orders(current, target_weights, portfolio_value, max_shares_map=max_shares_map)

    results = []
    for order in orders:
        ticker, side, qty = order["ticker"], order["side"], order["qty"]
        pos = current.get(ticker, {})

        if not check_position_limit(pos.get("market_value", 0.0), portfolio_value):
            log.warning("run_daily_rebalance: position limit exceeded, skipping", ticker=ticker)
            continue

        price = pos.get("price")
        if not price:
            continue

        if dry_run:
            results.append({**order, "submitted": False})
            continue

        fill = route_order(ticker, side, qty, price)
        if fill is None:
            results.append({**order, "submitted": False, "filled": False})
            continue

        slippage = compute_slippage_bps(fill["fill_price"], price, side)
        decision_id = log_decision(
            ticker=ticker,
            action=side,
            entry_price=fill["fill_price"],
            signals={"target_weight": target_weights.get(ticker, 0.0)},
            debate_summary=order.get("reason", ""),
            regime=regime,
        )
        trade_id = log_trade(
            ticker=ticker,
            side=side,
            qty=qty,
            order_type="limit",
            limit_price=price,
            fill_price=fill["fill_price"],
            slippage_bps=slippage,
            signals={"target_weight": target_weights.get(ticker, 0.0)},
            risk_snapshot={"max_shares": max_shares_map.get(ticker), "portfolio_corr": portfolio_corr},
            rationale=order.get("reason", ""),
        )
        results.append({
            **order,
            "decision_id": decision_id,
            "trade_id": trade_id,
            "submitted": True,
            "fill_price": fill["fill_price"],
        })

    log_activity("daily_trader", "run_daily_rebalance", "ok", orders=len(results), dry_run=dry_run)
    return {"status": "ok", "orders": results, "dry_run": dry_run}
