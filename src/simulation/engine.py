"""Trade simulator engine.

Runs daily after run_ensemble_pipeline() writes today's ensemble_scores. Reads
the same target weights as daily_trader, but executes against a $100K virtual
portfolio stored in sim_config/sim_positions/sim_trades — no broker calls.

Prices come from ohlcv_daily (adj_close), so the step is offline-safe and
deterministic. Position sizing reuses compute_rebalance_orders with the sim
portfolio value substituted for real equity.
"""
from __future__ import annotations

import math
from datetime import date

from ..core.db import conn
from ..core.logging import get_logger, log_activity
from ..risk.position_sizer import compute_max_shares
from ..risk.rebalancer import compute_rebalance_orders

log = get_logger("sim_engine")

STARTING_CAPITAL = 100_000.0


# ── Config helpers ───────────────────────────────────────────────────────────

def _ensure_config(cur) -> None:
    cur.execute(
        "INSERT INTO sim_config (id, starting_capital, cash, enabled) "
        "VALUES (1, %s, %s, FALSE) ON CONFLICT (id) DO NOTHING",
        (STARTING_CAPITAL, STARTING_CAPITAL),
    )


def is_sim_enabled() -> bool:
    with conn() as c, c.cursor() as cur:
        _ensure_config(cur)
        cur.execute("SELECT enabled FROM sim_config WHERE id = 1")
        row = cur.fetchone()
    return bool(row[0]) if row else False


def set_sim_enabled(enabled: bool) -> None:
    with conn() as c, c.cursor() as cur:
        _ensure_config(cur)
        cur.execute(
            "UPDATE sim_config SET enabled = %s, updated_at = NOW() WHERE id = 1",
            (enabled,),
        )
        c.commit()
    log_activity("sim_engine", "toggle", "ok", enabled=enabled)


def reset_sim() -> dict:
    """Wipe all sim data and restore $100K starting balance."""
    with conn() as c, c.cursor() as cur:
        cur.execute("DELETE FROM sim_weekly_reports")
        cur.execute("DELETE FROM sim_snapshots")
        cur.execute("DELETE FROM sim_trades")
        cur.execute("DELETE FROM sim_positions")
        cur.execute(
            "UPDATE sim_config SET cash = starting_capital, updated_at = NOW() WHERE id = 1"
        )
        c.commit()
    log_activity("sim_engine", "reset", "ok")
    return {"status": "reset", "starting_capital": STARTING_CAPITAL}


# ── Internal helpers ─────────────────────────────────────────────────────────

def _get_vol_60d(ticker: str) -> float:
    """Most recent vol_20d from features_daily. Defaults to 20% (middle tier) if missing."""
    with conn() as c, c.cursor() as cur:
        cur.execute(
            "SELECT value FROM features_daily WHERE ticker = %s AND feature_name = 'vol_20d' "
            "ORDER BY date DESC LIMIT 1",
            (ticker,),
        )
        row = cur.fetchone()
    return float(row[0]) if row and row[0] is not None else 0.20


def _get_prices(tickers: set[str]) -> dict[str, float]:
    if not tickers:
        return {}
    prices: dict[str, float] = {}
    with conn() as c, c.cursor() as cur:
        for ticker in tickers:
            cur.execute(
                "SELECT adj_close FROM ohlcv_daily WHERE ticker = %s AND adj_close IS NOT NULL "
                "ORDER BY date DESC LIMIT 1",
                (ticker,),
            )
            row = cur.fetchone()
            if row:
                prices[ticker] = float(row[0])
    return prices


def _sim_buy(cur, ticker: str, qty: int, price: float, today: date, target_weight: float) -> None:
    notional = qty * price
    cur.execute(
        """
        INSERT INTO sim_positions (ticker, qty, avg_cost, cost_basis, first_entry, last_updated)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (ticker) DO UPDATE
          SET qty          = sim_positions.qty + EXCLUDED.qty,
              avg_cost     = (sim_positions.cost_basis + EXCLUDED.cost_basis)
                             / (sim_positions.qty + EXCLUDED.qty),
              cost_basis   = sim_positions.cost_basis + EXCLUDED.cost_basis,
              last_updated = EXCLUDED.last_updated
        """,
        (ticker, qty, price, notional, today, today),
    )
    cur.execute(
        "INSERT INTO sim_trades (date, ticker, side, qty, price, notional, target_weight) "
        "VALUES (%s, %s, 'buy', %s, %s, %s, %s)",
        (today, ticker, qty, price, notional, target_weight),
    )


def _sim_sell(cur, ticker: str, qty: int, price: float, today: date,
              avg_cost: float, target_weight: float) -> float:
    """Returns realized P/L for this sell."""
    notional = qty * price
    realized_pnl = (price - avg_cost) * qty
    cur.execute(
        "INSERT INTO sim_trades (date, ticker, side, qty, price, notional, realized_pnl, target_weight) "
        "VALUES (%s, %s, 'sell', %s, %s, %s, %s, %s)",
        (today, ticker, qty, price, notional, realized_pnl, target_weight),
    )
    cur.execute("SELECT qty, cost_basis FROM sim_positions WHERE ticker = %s", (ticker,))
    row = cur.fetchone()
    if row is None:
        return realized_pnl
    current_qty, current_cost_basis = int(row[0]), float(row[1])
    new_qty = current_qty - qty
    if new_qty <= 0:
        cur.execute("DELETE FROM sim_positions WHERE ticker = %s", (ticker,))
    else:
        cost_reduction = qty * avg_cost
        cur.execute(
            "UPDATE sim_positions SET qty = %s, cost_basis = cost_basis - %s, last_updated = %s "
            "WHERE ticker = %s",
            (new_qty, cost_reduction, today, ticker),
        )
    return realized_pnl


# ── Main step ────────────────────────────────────────────────────────────────

def run_sim_step() -> dict:
    """Execute one daily sim step. Safe to run multiple times (snapshot upserts)."""
    if not is_sim_enabled():
        return {"status": "disabled"}

    today = date.today()

    with conn() as c, c.cursor() as cur:
        cur.execute(
            """
            SELECT ticker, target_weight FROM ensemble_scores
            WHERE date = (SELECT MAX(date) FROM ensemble_scores WHERE date <= %s)
            """,
            (today,),
        )
        score_rows = cur.fetchall()

    if not score_rows:
        log.info("run_sim_step: no ensemble_scores for today")
        return {"status": "no_scores"}

    target_weights = {t: float(w) for t, w in score_rows if w is not None}

    with conn() as c, c.cursor() as cur:
        _ensure_config(cur)
        cur.execute("SELECT cash, starting_capital FROM sim_config WHERE id = 1")
        cfg = cur.fetchone()
        cash = float(cfg[0])
        starting_capital = float(cfg[1])

        cur.execute("SELECT ticker, qty, avg_cost, cost_basis FROM sim_positions")
        open_rows = cur.fetchall()

    open_positions = {
        r[0]: {"qty": int(r[1]), "avg_cost": float(r[2]), "cost_basis": float(r[3])}
        for r in open_rows
    }

    all_tickers = set(target_weights.keys()) | set(open_positions.keys())
    prices = _get_prices(all_tickers)

    positions_value = sum(
        pos["qty"] * prices.get(t, pos["avg_cost"])
        for t, pos in open_positions.items()
    )
    portfolio_value = cash + positions_value

    # Build current dict for rebalancer
    current: dict = {}
    for ticker, pos in open_positions.items():
        price = prices.get(ticker, pos["avg_cost"])
        current[ticker] = {"qty": pos["qty"], "price": price, "market_value": pos["qty"] * price}
    for ticker in target_weights:
        if ticker not in current and ticker in prices:
            current[ticker] = {"qty": 0, "price": prices[ticker], "market_value": 0.0}

    # Mirror the real trader's per-ticker volatility cap so sim position sizes match.
    from ..risk.correlation import compute_portfolio_correlation
    portfolio_corr = (
        compute_portfolio_correlation(list(current.keys()))
        if len(current) >= 2 else 0.0
    )
    max_shares_map = {
        ticker: compute_max_shares(
            ticker, portfolio_value,
            pos["price"], _get_vol_60d(ticker), portfolio_corr,
        )
        for ticker, pos in current.items()
        if pos["price"] > 0
    }
    orders = compute_rebalance_orders(
        current, target_weights, portfolio_value, max_shares_map=max_shares_map
    )

    bought, sold = 0, 0
    with conn() as c, c.cursor() as cur:
        for order in orders:
            ticker = order["ticker"]
            side = order["side"]
            qty = order["qty"]
            price = prices.get(ticker)
            if not price or qty <= 0:
                continue
            target_weight = target_weights.get(ticker, 0.0)

            if side == "buy":
                affordable_qty = min(qty, int(cash / price))
                if affordable_qty <= 0:
                    continue
                _sim_buy(cur, ticker, affordable_qty, price, today, target_weight)
                cash -= affordable_qty * price
                bought += 1
            else:
                held = open_positions.get(ticker, {})
                sell_qty = min(qty, held.get("qty", 0))
                if sell_qty <= 0:
                    continue
                _sim_sell(cur, ticker, sell_qty, price, today,
                          held.get("avg_cost", price), target_weight)
                cash += sell_qty * price
                sold += 1

        cur.execute(
            "UPDATE sim_config SET cash = %s, updated_at = NOW() WHERE id = 1", (cash,)
        )

        # Recompute positions value after trades
        cur.execute("SELECT ticker, qty FROM sim_positions")
        new_open = {r[0]: int(r[1]) for r in cur.fetchall()}
        new_positions_value = sum(
            qty * prices.get(ticker, 0.0) for ticker, qty in new_open.items()
        )
        total_value = cash + new_positions_value

        cur.execute("SELECT MAX(total_value) FROM sim_snapshots")
        peak_row = cur.fetchone()
        peak = max(float(peak_row[0]), total_value) if peak_row and peak_row[0] is not None else total_value
        drawdown = (total_value - peak) / peak if peak > 0 else 0.0

        cur.execute(
            "SELECT total_value FROM sim_snapshots WHERE date < %s ORDER BY date DESC LIMIT 1",
            (today,),
        )
        prev_row = cur.fetchone()
        prev_value = float(prev_row[0]) if prev_row else starting_capital
        daily_return = (total_value - prev_value) / prev_value if prev_value > 0 else 0.0
        cumulative_return = (total_value - starting_capital) / starting_capital if starting_capital > 0 else 0.0

        cur.execute(
            """
            INSERT INTO sim_snapshots
                (date, cash, positions_value, total_value, daily_return,
                 cumulative_return, drawdown, open_positions)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (date) DO UPDATE
              SET cash              = EXCLUDED.cash,
                  positions_value   = EXCLUDED.positions_value,
                  total_value       = EXCLUDED.total_value,
                  daily_return      = EXCLUDED.daily_return,
                  cumulative_return = EXCLUDED.cumulative_return,
                  drawdown          = EXCLUDED.drawdown,
                  open_positions    = EXCLUDED.open_positions
            """,
            (today, cash, new_positions_value, total_value, daily_return,
             cumulative_return, drawdown, len(new_open)),
        )
        c.commit()

    log_activity(
        "sim_engine", "run_sim_step", "ok",
        bought=bought, sold=sold,
        total_value=round(total_value, 2),
        drawdown=round(drawdown, 4),
    )

    if today.weekday() == 4:  # Friday → generate weekly report
        from .reports import generate_weekly_report
        generate_weekly_report(week_ending=today)

    return {
        "status": "ok",
        "bought": bought,
        "sold": sold,
        "cash": round(cash, 2),
        "positions_value": round(new_positions_value, 2),
        "total_value": round(total_value, 2),
        "daily_return": round(daily_return, 6),
        "drawdown": round(drawdown, 6),
    }
