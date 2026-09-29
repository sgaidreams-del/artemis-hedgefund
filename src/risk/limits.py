"""Risk limit checks — drawdown, position, sector, beta."""
from __future__ import annotations

from src.core.config import settings
from src.core.db import conn
from src.core.logging import get_logger

log = get_logger(__name__)


def check_drawdown_limits(
    value: float,
    initial: float,
    weekly_low: float | None = None,
) -> str:
    """Return 'ok', 'reduce_risk', or 'halt' based on drawdown thresholds.

    Guard against initial=0 (return 'ok').
    daily_drawdown_halt = -0.03 (from cfg), max_drawdown_liquidate = -0.15.
    If drawdown < -0.15: 'halt'. If < -0.03: 'reduce_risk'. Else: 'ok'.
    """
    if initial == 0:
        log.warning("check_drawdown_limits: initial=0, skipping check")
        return "ok"

    cfg = settings()
    daily_halt = cfg["risk"]["daily_drawdown_halt"]          # -0.03
    max_liquidate = cfg["risk"]["max_drawdown_liquidate"]     # -0.15

    drawdown = (value - initial) / initial

    log.debug("check_drawdown_limits", drawdown=drawdown, daily_halt=daily_halt, max_liquidate=max_liquidate)

    if drawdown < max_liquidate:
        return "halt"
    if drawdown < daily_halt:
        return "reduce_risk"
    return "ok"


def _previous_close_value() -> float | None:
    """Most recent prior day's total_value from portfolio_snapshots, or None
    if there's no history yet (e.g. bootstrap day)."""
    with conn() as c, c.cursor() as cur:
        cur.execute(
            "SELECT total_value FROM portfolio_snapshots WHERE date < CURRENT_DATE "
            "ORDER BY date DESC LIMIT 1"
        )
        row = cur.fetchone()
    return float(row[0]) if row and row[0] is not None else None


def _peak_value(current_equity: float) -> float:
    """All-time-high total_value, including today's live equity if it's a new high."""
    with conn() as c, c.cursor() as cur:
        cur.execute("SELECT MAX(total_value) FROM portfolio_snapshots")
        row = cur.fetchone()
    historical_peak = float(row[0]) if row and row[0] is not None else 0.0
    return max(historical_peak, current_equity)


def check_daily_loss_halt(current_equity: float) -> bool:
    """True if today's equity has dropped past risk.daily_drawdown_halt vs
    yesterday's close. False (no breach) if there's no prior snapshot yet —
    a halt needs a baseline to compare against."""
    prev = _previous_close_value()
    if prev is None or prev == 0:
        return False
    cfg = settings()
    threshold = cfg["risk"]["daily_drawdown_halt"]  # e.g. -0.03
    session_return = (current_equity - prev) / prev
    return session_return < threshold


def check_trailing_drawdown_halt(current_equity: float) -> bool:
    """True if current equity has dropped past risk.max_drawdown_liquidate
    from the all-time peak. Behavior on breach is freeze (per settings.yaml
    risk.breach_behavior), not literal liquidation, despite the key name."""
    peak = _peak_value(current_equity)
    if peak == 0:
        return False
    cfg = settings()
    threshold = cfg["risk"]["max_drawdown_liquidate"]  # e.g. -0.15
    drawdown = (current_equity - peak) / peak
    return drawdown < threshold


def check_consecutive_loss_halt() -> bool:
    """True if the trailing N days (risk.consecutive_loss_days_halt) all had
    a negative daily_return. Looks at closed days only — today's in-progress
    snapshot isn't written yet when this runs pre-trade."""
    cfg = settings()
    n = cfg["risk"]["consecutive_loss_days_halt"]
    with conn() as c, c.cursor() as cur:
        cur.execute(
            "SELECT daily_return FROM portfolio_snapshots WHERE date < CURRENT_DATE "
            "ORDER BY date DESC LIMIT %s",
            (n,),
        )
        rows = cur.fetchall()
    if len(rows) < n:
        return False
    return all(r[0] is not None and float(r[0]) < 0 for r in rows)


def check_cash_floor(account: dict) -> bool:
    """True if the account's cash buffer has dropped below portfolio.min_cash_pct
    of equity — the buying-power floor that was defined in settings.yaml but
    never actually checked anywhere."""
    equity = account.get("equity") or 0.0
    cash = account.get("cash") or 0.0
    if equity <= 0:
        return False
    cfg = settings()
    min_cash_pct = cfg["portfolio"]["min_cash_pct"]
    return (cash / equity) < min_cash_pct


def check_exposure_limits(positions: list[dict], account: dict) -> bool:
    """True if gross exposure (sum of |market_value| across positions) divided
    by equity exceeds portfolio.max_gross_leverage. This is a cash account —
    the cap defaults to 1.0 (no margin)."""
    equity = account.get("equity") or 0.0
    if equity <= 0:
        return False
    gross = sum(abs(p.get("market_value") or 0.0) for p in positions)
    cfg = settings()
    cap = cfg["portfolio"]["max_gross_leverage"]
    return (gross / equity) > cap


def check_greeks_limits(delta_exposure: float, portfolio_value: float) -> bool:
    """True if book-level delta-equivalent exposure (see
    execution.options.delta_equivalent_exposure) exceeds risk.max_delta_exposure_pct
    of portfolio value. Per-order gate (called from submit_option_order), so —
    like the rest of the pre-trade gate — an unknown portfolio value fails
    closed rather than silently passing.

    Degrades to always-passing-when-known while delta_snapshot is unpopulated
    (exposure computes to 0) — the mechanism is real and activates the moment
    Greeks data starts being captured."""
    if portfolio_value <= 0:
        return True
    cfg = settings()
    cap = cfg["risk"]["max_delta_exposure_pct"]
    return (abs(delta_exposure) / portfolio_value) > cap


def check_underlying_concentration(existing_notional: float, new_notional: float, portfolio_value: float) -> bool:
    """True if existing + new notional for one underlying (summed across every
    contract — any strike, expiry, or call/put — on that underlying) would
    exceed portfolio.max_position_pct. Same concentration limit as a single
    equity position, just option-aware: many contracts on one underlying are
    one concentrated bet, not several independent small ones."""
    if portfolio_value <= 0:
        return True
    cfg = settings()
    cap = cfg["portfolio"]["max_position_pct"]
    return ((existing_notional + new_notional) / portfolio_value) > cap


def check_position_limit(pos_value: float, portfolio_value: float) -> bool:
    """Return True if position is within the max single-position limit.

    pos_value / portfolio_value <= max_position_pct (0.05 by default).
    """
    if portfolio_value <= 0:
        return False
    cfg = settings()
    max_pct = cfg["portfolio"]["max_position_pct"]
    return (pos_value / portfolio_value) <= max_pct


def check_sector_limit(
    current_sector_value: float,
    new_pos_value: float,
    portfolio_value: float,
    sector_limit: float = 0.25,
) -> bool:
    """Return True if adding new_pos_value keeps the sector under sector_limit (25%)."""
    if portfolio_value <= 0:
        return False
    total_sector = current_sector_value + new_pos_value
    return (total_sector / portfolio_value) <= sector_limit


def check_beta_limit(beta: float, max_beta: float = 1.3) -> bool:
    """Return True if beta is within the acceptable maximum."""
    return beta <= max_beta
