"""Manual rebalance trigger — preview and execute, both human-initiated only.

There is no scheduled/automatic endpoint here. Preview always runs
dry_run=True (no broker calls). Execute runs dry_run=False and actually
routes orders to the (paper) broker — it exists so a human can click a
button to do deliberately what they could otherwise do from a terminal;
nothing here fires on its own.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter

router = APIRouter(prefix="/api/trading", tags=["trading"])
log = logging.getLogger(__name__)


@router.post("/rebalance/preview")
def preview_rebalance():
    """Compute today's rebalance orders without submitting anything."""
    try:
        from src.execution.daily_trader import run_daily_rebalance
        return run_daily_rebalance(dry_run=True)
    except Exception as exc:
        log.exception("rebalance preview failed")
        return {"status": "error", "error": str(exc), "orders": []}


@router.post("/rebalance/execute")
def execute_rebalance():
    """Submit today's rebalance orders to the broker. Real (paper) orders."""
    try:
        from src.execution.daily_trader import run_daily_rebalance
        return run_daily_rebalance(dry_run=False)
    except Exception as exc:
        log.exception("rebalance execute failed")
        return {"status": "error", "error": str(exc), "orders": []}
