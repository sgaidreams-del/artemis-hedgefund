"""Single fail-closed pre-trade gate.

EVERY order — equity or option, paper or live — must pass through
pretrade_check() before it leaves. The gate fails CLOSED: any check that
errors, or any required input that is missing, rejects the order rather
than letting it through.

Design notes:
- Per-order checks live here so there is exactly one place to reason about
  "is this order safe to send." The equity path (order_router) and the
  options path (execution.options) both call in, so neither can bypass it.
- The same gate runs in paper and live — only the broker endpoint differs.
  That is deliberate: for paper results to predict live results, the order
  path that produces them must be identical.
- Each check is independently testable; tests/test_pretrade.py deliberately
  trips each one. "Untested safeguards are decoration."
"""
from __future__ import annotations

import hashlib
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from dashboard_api.routers.kill_switch import is_paused
from src.core.config import settings
from src.core.db import conn
from src.core.logging import get_logger

log = get_logger("pretrade")


class RiskConfigError(RuntimeError):
    """Raised at startup when a required risk limit is missing or absurd."""


# ── Order representation ──────────────────────────────────────────────────────

@dataclass
class OrderIntent:
    symbol: str            # equity ticker or OCC option symbol
    side: str              # "buy" | "sell"
    qty: int
    limit_price: float
    asset_class: str = "equity"   # "equity" | "option"
    underlying: str | None = None  # defaults to symbol for equities
    client_order_id: str | None = None

    def __post_init__(self) -> None:
        if self.underlying is None:
            self.underlying = self.symbol if self.asset_class == "equity" else self.symbol[:6].strip()
        if self.client_order_id is None:
            self.client_order_id = make_client_order_id(self)


def make_client_order_id(order: OrderIntent, trade_date: date | None = None) -> str:
    """Deterministic id for an order intent, stable per (day, symbol, side, qty, price).

    Resends of the same logical order on the same day collapse to one id, so the
    idempotency guard rejects double-submits and reconnect-retries.
    """
    d = (trade_date or date.today()).isoformat()
    cents = int(round(order.limit_price * 100))
    payload = f"{d}|{order.symbol}|{order.side}|{order.qty}|{cents}|{order.asset_class}"
    return "art-" + hashlib.sha1(payload.encode()).hexdigest()[:24]


# ── Results ───────────────────────────────────────────────────────────────────

@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class PreTradeDecision:
    allow: bool
    reason: str
    checks: list[CheckResult] = field(default_factory=list)


# ── Rate limiter (in-process sliding window — catches runaway loops) ──────────

_order_times: deque[float] = deque()
_rate_lock = threading.Lock()


def _reset_rate_limiter() -> None:
    """Test hook."""
    with _rate_lock:
        _order_times.clear()


def _rate_limit_ok(now: float, max_per_minute: int) -> bool:
    """Sliding 60s window. Records the timestamp only if under the cap."""
    with _rate_lock:
        cutoff = now - 60.0
        while _order_times and _order_times[0] < cutoff:
            _order_times.popleft()
        if len(_order_times) >= max_per_minute:
            return False
        _order_times.append(now)
        return True


# ── Idempotency (persisted; check-and-record is atomic) ──────────────────────

def _claim_idempotency(order: OrderIntent) -> bool:
    """Insert the client_order_id; return True if newly claimed, False if a
    duplicate (already present). DB error → False (fail closed)."""
    try:
        with conn() as c, c.cursor() as cur:
            cur.execute(
                """
                INSERT INTO submitted_orders (client_order_id, symbol, side, qty, limit_price, asset_class)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (client_order_id) DO NOTHING
                RETURNING client_order_id
                """,
                (order.client_order_id, order.symbol, order.side, order.qty,
                 order.limit_price, order.asset_class),
            )
            row = cur.fetchone()
            c.commit()
        return row is not None
    except Exception:
        log.exception("idempotency claim failed — rejecting (fail closed)")
        return False


# ── The gate ──────────────────────────────────────────────────────────────────

def pretrade_check(
    order: OrderIntent,
    *,
    reference_price: float | None,
    market_open: bool | None,
    now: float | None = None,
    quote_age_seconds: float | None = None,
) -> PreTradeDecision:
    """Run every pre-trade check, fail-closed. Returns allow/reject + per-check trace.

    reference_price: an independently-fetched current price for the collar.
        None means "could not be obtained" — for equities that is a hard reject;
        for options (no quote feed wired yet) the collar is skipped with a warning.
    market_open: True/False from the broker clock, or None if it couldn't be read
        (None → reject when require_market_open is set).
    quote_age_seconds: age of the reference quote. None means "unknown" — for
        equities (where a quote feed exists) that's a hard reject; options skip
        this the same way they skip the collar, for the same reason.
    """
    now = now if now is not None else time.time()
    cfg = settings()
    ex = cfg["execution"]
    checks: list[CheckResult] = []

    def run(name: str, fn) -> bool:
        try:
            ok, detail = fn()
        except Exception as e:  # any error in a check → that check fails (closed)
            ok, detail = False, f"check raised: {e}"
        checks.append(CheckResult(name, ok, detail))
        return ok

    # 1. Kill switch
    run("kill_switch", lambda: (not is_paused(), "paused" if is_paused() else "active"))

    # 2. Quantity sane
    run("qty_valid", lambda: (
        isinstance(order.qty, int) and order.qty > 0,
        f"qty={order.qty}",
    ))

    # 3. Max order quantity
    run("max_qty", lambda: (
        order.qty <= ex["max_order_qty"],
        f"qty={order.qty} cap={ex['max_order_qty']}",
    ))

    # 4. Max order notional
    run("max_notional", lambda: (
        order.qty * order.limit_price <= ex["max_order_notional"],
        f"notional={order.qty * order.limit_price:.0f} cap={ex['max_order_notional']}",
    ))

    # 5. Price collar (vs an independent reference)
    def _collar():
        if reference_price is None:
            if order.asset_class == "option":
                # No options quote feed wired yet — collar deferred (Phase later).
                log.warning("price collar skipped for option %s — no reference quote", order.symbol)
                return True, "skipped: no option reference quote"
            return False, "no reference price (equity) — fail closed"
        if reference_price <= 0:
            return False, f"non-positive reference {reference_price}"
        dev = abs(order.limit_price - reference_price) / reference_price
        return dev <= ex["price_collar_pct"], f"dev={dev:.4f} cap={ex['price_collar_pct']} ref={reference_price}"
    run("price_collar", _collar)

    # 5b. Data staleness — the quote backing the collar must itself be fresh.
    def _staleness():
        if order.asset_class == "option":
            # Same reasoning as the collar: no options quote feed wired yet.
            return True, "skipped: no option reference quote"
        if quote_age_seconds is None:
            return False, "quote age unknown — fail closed"
        max_age = ex["max_quote_age_seconds"]
        return quote_age_seconds <= max_age, f"age={quote_age_seconds:.1f}s cap={max_age}s"
    run("data_staleness", _staleness)

    # 6. Market hours
    def _hours():
        if not ex.get("require_market_open", True):
            return True, "market-hours check disabled"
        if market_open is None:
            return False, "clock unavailable — fail closed"
        return bool(market_open), "open" if market_open else "closed"
    run("market_hours", _hours)

    # 7. Rate limit (runaway-loop guard)
    run("rate_limit", lambda: (
        _rate_limit_ok(now, ex["max_orders_per_minute"]),
        f"cap={ex['max_orders_per_minute']}/min",
    ))

    # 8. Idempotency — LAST, because it records. Only consume the id if every
    #    other check passed, so a rejected order doesn't burn its idempotency slot.
    if all(c.passed for c in checks):
        run("idempotency", lambda: (
            _claim_idempotency(order),
            f"client_order_id={order.client_order_id}",
        ))
    else:
        checks.append(CheckResult("idempotency", False, "skipped — earlier check failed"))

    allow = all(c.passed for c in checks)
    reason = "ok" if allow else "; ".join(f"{c.name}:{c.detail}" for c in checks if not c.passed)
    if not allow:
        log.warning("pretrade REJECT %s %s x%d @ %.4f — %s",
                    order.side, order.symbol, order.qty, order.limit_price, reason)
    return PreTradeDecision(allow=allow, reason=reason, checks=checks)


# ── Live wrappers (fetch reference + clock, then call the gate) ───────────────

def check_equity_order(order: OrderIntent) -> PreTradeDecision:
    """Equity gate: independently fetch the reference quote and market clock."""
    from src.execution.broker import get_latest_quote, is_market_open
    quote = get_latest_quote(order.symbol)   # None → collar and staleness both fail closed
    return pretrade_check(
        order,
        reference_price=quote["price"] if quote else None,
        market_open=is_market_open(),
        quote_age_seconds=quote["age_seconds"] if quote else None,
    )


def check_option_order(order: OrderIntent, reference_price: float | None = None) -> PreTradeDecision:
    """Options gate: caller may supply a reference (option mid). Collar is
    skipped-with-warning when none is available; all other checks still apply,
    including the kill switch the options path previously bypassed entirely."""
    from src.execution.broker import is_market_open
    return pretrade_check(order, reference_price=reference_price, market_open=is_market_open())


# ── Startup config validation (crash loudly, never default to "no limit") ────

def validate_risk_config() -> None:
    """Refuse to operate if any required risk/execution limit is missing, zeroed,
    or absurd. Call before any trading entry point."""
    cfg = settings()
    errors: list[str] = []

    def need(section: str, key: str, predicate, desc: str):
        try:
            val = cfg[section][key]
        except (KeyError, TypeError):
            errors.append(f"{section}.{key} is missing")
            return
        if val is None or not predicate(val):
            errors.append(f"{section}.{key}={val!r} is invalid ({desc})")

    need("portfolio", "max_position_pct", lambda v: 0 < v <= 1, "0 < x <= 1")
    need("portfolio", "min_cash_pct", lambda v: 0 <= v < 1, "0 <= x < 1")
    need("portfolio", "max_gross_leverage", lambda v: 0 < v <= 4, "0 < x <= 4 (cash account)")
    need("risk", "daily_drawdown_halt", lambda v: v < 0, "must be negative")
    need("risk", "max_drawdown_liquidate", lambda v: v < 0, "must be negative")
    need("risk", "breach_behavior", lambda v: v in ("freeze", "flatten"), "freeze|flatten")
    need("risk", "consecutive_loss_days_halt", lambda v: isinstance(v, int) and v > 0, "positive int")
    need("risk", "max_delta_exposure_pct", lambda v: 0 < v <= 1, "0 < x <= 1")
    need("execution", "max_order_qty", lambda v: v > 0, "> 0")
    need("execution", "max_order_notional", lambda v: v > 0, "> 0")
    need("execution", "price_collar_pct", lambda v: 0 < v < 1, "0 < x < 1")
    need("execution", "max_orders_per_minute", lambda v: v > 0, "> 0")
    need("execution", "max_quote_age_seconds", lambda v: v > 0, "> 0")

    if errors:
        msg = "Risk config invalid — refusing to trade:\n  - " + "\n  - ".join(errors)
        log.error(msg)
        raise RiskConfigError(msg)
    log.info("risk config validated", checked=13)
