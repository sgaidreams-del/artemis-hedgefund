"""Alpaca options execution (Phase B). Wraps alpaca-py for options order management.

Options trading requires Tier 1+ approval on the Alpaca paper account.
All orders are limit orders (never market) per SPEC §9 execution design.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache

import yfinance as yf

from ..core.config import env
from ..core.db import conn

logger = logging.getLogger(__name__)


def options_configured() -> bool:
    """True only when all three options-execution env vars are present and enabled."""
    return bool(
        env("ALPACA_API_KEY")
        and env("ALPACA_API_SECRET")
        and env("OPTIONS_EXECUTION_ENABLED", "false").lower() == "true"
    )


@lru_cache(maxsize=1)
def _options_client():
    """Return a TradingClient configured for options, or None if not enabled."""
    if not options_configured():
        return None
    try:
        from alpaca.trading.client import TradingClient

        return TradingClient(
            api_key=env("ALPACA_API_KEY"),
            secret_key=env("ALPACA_API_SECRET"),
            paper=env("ENVIRONMENT", "paper") != "live",
        )
    except Exception:
        logger.exception("Failed to build options TradingClient")
        return None


def get_options_chain(
    underlying: str,
    expiry_min_days: int = 14,
    expiry_max_days: int = 60,
) -> list[dict]:
    """Return options chains for expirations between min and max days out."""
    try:
        t = yf.Ticker(underlying)
        all_expiries = t.options
        if not all_expiries:
            return []

        today = date.today()
        lo = today + timedelta(days=expiry_min_days)
        hi = today + timedelta(days=expiry_max_days)

        result: list[dict] = []
        for exp_str in all_expiries:
            exp_date = date.fromisoformat(exp_str)
            if not (lo <= exp_date <= hi):
                continue
            try:
                chain = t.option_chain(exp_str)
                result.append(
                    {
                        "expiry": exp_str,
                        "calls": chain.calls.to_dict("records"),
                        "puts": chain.puts.to_dict("records"),
                    }
                )
            except Exception:
                logger.exception("option_chain fetch failed", extra={"expiry": exp_str})
        return result
    except Exception:
        logger.exception("get_options_chain failed", extra={"underlying": underlying})
        return []


def find_option(
    underlying: str,
    option_type: str,
    target_delta: float = 0.40,
    expiry_min_days: int = 21,
    expiry_max_days: int = 45,
) -> dict | None:
    """Find the contract closest to target_delta within the expiry window.

    Delta proxy: ATM ≈ 0.50; we use (strike - price)/price to rank OTM distance,
    then map to an approximate delta via the normal CDF of that relative distance.
    """
    try:
        import math

        chains = get_options_chain(underlying, expiry_min_days, expiry_max_days)
        if not chains:
            return None

        t = yf.Ticker(underlying)
        hist = t.history(period="1d")
        if hist.empty:
            return None
        current_price = float(hist["Close"].iloc[-1])

        best: dict | None = None
        best_delta_err = float("inf")

        for chain_entry in chains:
            expiry = chain_entry["expiry"]
            rows = chain_entry["calls"] if option_type.lower() == "call" else chain_entry["puts"]

            for row in rows:
                strike = float(row.get("strike", 0))
                if strike <= 0:
                    continue

                # Simple delta proxy: Φ(0.4 - moneyness*5) for calls, 1-Φ for puts
                moneyness = (strike - current_price) / current_price
                if option_type.lower() == "call":
                    approx_delta = 0.5 * math.erfc(moneyness * 5 / math.sqrt(2))
                else:
                    approx_delta = 0.5 * math.erfc(-moneyness * 5 / math.sqrt(2))

                err = abs(approx_delta - target_delta)
                if err < best_delta_err:
                    best_delta_err = err
                    best = {
                        "symbol": occ_symbol(underlying, expiry, option_type, strike),
                        "underlying": underlying,
                        "option_type": option_type.lower(),
                        "strike": strike,
                        "expiry": expiry,
                        "lastPrice": row.get("lastPrice"),
                        "impliedVolatility": row.get("impliedVolatility"),
                        "openInterest": row.get("openInterest"),
                        "approx_delta": approx_delta,
                    }
        return best
    except Exception:
        logger.exception("find_option failed", extra={"underlying": underlying})
        return None


def occ_symbol(underlying: str, expiry: str, option_type: str, strike: float) -> str:
    """Format OCC option symbol: {ticker:6s}{YY}{MM}{DD}{C/P}{strike*1000:08d}.

    Example: AAPL  250117C00150000
    """
    exp = date.fromisoformat(expiry)
    cp = "C" if option_type.lower() == "call" else "P"
    strike_int = int(round(strike * 1000))
    return f"{underlying:<6s}{exp.strftime('%y%m%d')}{cp}{strike_int:08d}"


def submit_option_order(
    symbol: str,
    qty: int,
    side: str,
    limit_price: float,
    strategy_type: str = "directional",
) -> dict | None:
    """Submit a limit option order and record it in options_positions.

    Returns the order dict on success, None on failure.
    """
    client = _options_client()
    if client is None:
        logger.warning("options_configured=False — order not submitted: %s", symbol)
        return None

    # Fail-closed pre-trade gate — the options path previously bypassed the
    # kill switch and all risk checks entirely. Now it runs the same gate as
    # equities (collar is skipped-with-warning until an options quote feed is
    # wired; every other check, including the kill switch, applies).
    from src.risk.pretrade import OrderIntent, check_option_order
    decision = check_option_order(
        OrderIntent(symbol=symbol, side=side, qty=qty, limit_price=limit_price, asset_class="option")
    )
    if not decision.allow:
        logger.warning("option order REJECTED by pre-trade gate: %s — %s", symbol, decision.reason)
        return None

    # Book-level Greeks cap + per-underlying concentration. Both are options-
    # specific, so they live here rather than in the shared pre-trade gate.
    from src.execution.broker import get_account
    from src.risk.limits import check_greeks_limits, check_underlying_concentration

    account = get_account()
    portfolio_value = account["equity"] if account else 0.0

    underlying = symbol[:6].strip()
    open_positions = get_options_positions()
    new_notional = qty * limit_price * 100.0  # 100 shares/contract

    projected_delta = delta_equivalent_exposure(open_positions) + (
        qty * 100.0 * limit_price if side.lower() == "buy" else -qty * 100.0 * limit_price
    )
    # Best-effort: delta_snapshot is unpopulated on new orders, so this is
    # dominated by whatever existing positions already have a real delta.
    if check_greeks_limits(projected_delta, portfolio_value):
        logger.warning("option order REJECTED — book delta exposure cap: %s", symbol)
        return None

    existing_notional = sum(
        (p.get("qty") or 0) * (p.get("current_premium") or p.get("entry_premium") or 0.0) * 100.0
        for p in open_positions
        if (p.get("underlying") or p.get("symbol", "")[:6].strip()) == underlying
    )
    if check_underlying_concentration(existing_notional, new_notional, portfolio_value):
        logger.warning("option order REJECTED — underlying concentration cap: %s (%s)", symbol, underlying)
        return None

    try:
        from alpaca.trading.enums import AssetClass, OrderSide, TimeInForce
        from alpaca.trading.requests import LimitOrderRequest

        alpaca_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL
        req = LimitOrderRequest(
            symbol=symbol,
            qty=qty,
            side=alpaca_side,
            time_in_force=TimeInForce.DAY,
            limit_price=limit_price,
            asset_class=AssetClass.US_OPTION,
        )
        order = client.submit_order(req)
        order_dict = order.model_dump() if hasattr(order, "model_dump") else dict(order)

        # Parse OCC symbol for DB fields
        und = symbol[:6].strip()
        exp_str = f"20{symbol[6:8]}-{symbol[8:10]}-{symbol[10:12]}"
        opt_type = "call" if symbol[12] == "C" else "put"
        strike = int(symbol[13:]) / 1000.0

        with conn() as c, c.cursor() as cur:
            cur.execute(
                """
                INSERT INTO options_positions
                    (symbol, underlying, option_type, strike, expiry, qty,
                     entry_premium, strategy_type, opened_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (symbol) DO UPDATE
                  SET qty            = EXCLUDED.qty,
                      entry_premium  = EXCLUDED.entry_premium,
                      strategy_type  = EXCLUDED.strategy_type,
                      opened_at      = EXCLUDED.opened_at
                """,
                (symbol, und, opt_type, strike, exp_str, qty, limit_price, strategy_type),
            )
            c.commit()

        logger.info("option order submitted: %s %s x%d @ %.4f", side, symbol, qty, limit_price)
        return order_dict
    except Exception:
        logger.exception("submit_option_order failed", extra={"symbol": symbol})
        return None


def get_options_positions() -> list[dict]:
    """Return open options positions, cross-checked against Alpaca live positions."""
    try:
        with conn() as c, c.cursor() as cur:
            cur.execute(
                """
                SELECT id, symbol, underlying, option_type, strike, expiry, qty,
                       entry_premium, current_premium, delta_snapshot, strategy_type, opened_at
                FROM options_positions
                WHERE closed_at IS NULL
                """
            )
            cols = [d[0] for d in cur.description]
            db_rows = [dict(zip(cols, row)) for row in cur.fetchall()]

        db_by_symbol = {r["symbol"]: r for r in db_rows}

        client = _options_client()
        if client is not None:
            try:
                from alpaca.trading.enums import AssetClass

                live_positions = client.get_all_positions()
                for pos in live_positions:
                    if getattr(pos, "asset_class", None) == AssetClass.US_OPTION:
                        sym = pos.symbol
                        if sym in db_by_symbol:
                            db_by_symbol[sym]["current_premium"] = float(
                                getattr(pos, "current_price", 0) or 0
                            )
                        else:
                            # Position exists in Alpaca but not in DB — add it
                            db_by_symbol[sym] = {
                                "symbol": sym,
                                "qty": int(getattr(pos, "qty", 0)),
                                "current_premium": float(
                                    getattr(pos, "current_price", 0) or 0
                                ),
                                "source": "alpaca_only",
                            }
            except Exception:
                logger.exception("Alpaca positions cross-check failed — using DB only")

        return list(db_by_symbol.values())
    except Exception:
        logger.exception("get_options_positions failed")
        return []


def close_option_position(symbol: str, limit_price: float) -> dict | None:
    """Sell the position at limit_price and mark it closed in the DB."""
    try:
        with conn() as c, c.cursor() as cur:
            cur.execute(
                "SELECT qty FROM options_positions WHERE symbol=%s AND closed_at IS NULL",
                (symbol,),
            )
            row = cur.fetchone()
        if not row:
            logger.warning("close_option_position: no open position for %s", symbol)
            return None

        qty = int(row[0])
        order = submit_option_order(symbol, qty, "sell", limit_price)

        if order is not None:
            with conn() as c, c.cursor() as cur:
                cur.execute(
                    "UPDATE options_positions SET closed_at=NOW() WHERE symbol=%s",
                    (symbol,),
                )
                c.commit()
        return order
    except Exception:
        logger.exception("close_option_position failed", extra={"symbol": symbol})
        return None


def delta_equivalent_exposure(positions: list[dict]) -> float:
    """Sum of (qty × delta_snapshot × current_premium × 100) across open positions.

    100 = shares per contract. Returns dollar delta exposure.
    """
    total = 0.0
    for pos in positions:
        qty = pos.get("qty") or 0
        delta = pos.get("delta_snapshot") or 0.0
        premium = pos.get("current_premium") or pos.get("entry_premium") or 0.0
        total += qty * float(delta) * float(premium) * 100.0
    return total
