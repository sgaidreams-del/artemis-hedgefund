"""Reconciliation — compares the DB's view of open options positions against
what Alpaca actually reports.

Equities have no local shadow ledger to drift from (positions are always read
live from Alpaca in broker.get_positions()), so there's nothing to reconcile
there. Options are different: options.py writes options_positions on submit/
close, so that table can drift from the broker's actual book — and a drift
means something traded outside what we recorded, which is exactly the kind
of "something is wrong enough to halt" signal a kill switch exists for.
"""
from __future__ import annotations

from src.core.db import conn
from src.core.logging import get_logger, log_activity

log = get_logger("reconciliation")


def _db_options_positions() -> dict[str, int]:
    with conn() as c, c.cursor() as cur:
        cur.execute("SELECT symbol, qty FROM options_positions WHERE closed_at IS NULL")
        rows = cur.fetchall()
    return {symbol: int(qty) for symbol, qty in rows}


def _alpaca_options_positions() -> dict[str, int]:
    from src.execution.options import _options_client

    client = _options_client()
    if client is None:
        return {}
    try:
        from alpaca.trading.enums import AssetClass

        positions = client.get_all_positions()
        return {
            p.symbol: int(p.qty)
            for p in positions
            if getattr(p, "asset_class", None) == AssetClass.US_OPTION
        }
    except Exception:
        log.exception("reconcile_options: failed to fetch Alpaca positions")
        return {}


def reconcile_options() -> list[str]:
    """Compare DB vs Alpaca options books. Returns a list of finding strings
    (empty if everything matches). Alerts on every finding; engages the kill
    switch on a qty mismatch specifically — the case where the books don't
    just disagree on existence but on how much is actually held."""
    db_positions = _db_options_positions()
    alpaca_positions = _alpaca_options_positions()

    findings: list[str] = []
    qty_mismatch = False

    for symbol, db_qty in db_positions.items():
        if symbol not in alpaca_positions:
            findings.append(f"orphaned_db: {symbol} (db qty={db_qty}, not at broker)")
        elif alpaca_positions[symbol] != db_qty:
            findings.append(
                f"qty_mismatch: {symbol} (db={db_qty}, broker={alpaca_positions[symbol]})"
            )
            qty_mismatch = True

    for symbol, alpaca_qty in alpaca_positions.items():
        if symbol not in db_positions:
            findings.append(f"untracked_alpaca: {symbol} (broker qty={alpaca_qty}, not in db)")

    for finding in findings:
        log_activity("reconciliation", "mismatch", status="alert", finding=finding)
        log.warning(f"reconcile_options: {finding}")

    if qty_mismatch:
        from dashboard_api.routers.kill_switch import engage

        engage(f"reconciliation qty mismatch: {'; '.join(f for f in findings if f.startswith('qty_mismatch'))}")

    return findings
