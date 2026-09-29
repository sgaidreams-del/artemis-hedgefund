"""Daily portfolio snapshot writer.

portfolio_snapshots has no other writer — without this, the trailing-drawdown
and consecutive-loss-day halts in src/risk/limits.py have no history to check
against. Run once per pipeline cycle (see scripts/run_pipeline.py).
"""
from __future__ import annotations

from datetime import date

from psycopg.types.json import Json

from ..core.db import conn
from ..core.logging import get_logger
from ..execution.broker import get_account, get_positions

log = get_logger("snapshots")


def _previous_snapshot() -> tuple[float, float] | None:
    """(total_value, cumulative_return) of the most recent prior day, or None."""
    with conn() as c, c.cursor() as cur:
        cur.execute(
            "SELECT total_value, cumulative_return FROM portfolio_snapshots "
            "WHERE date < %s ORDER BY date DESC LIMIT 1",
            (date.today(),),
        )
        row = cur.fetchone()
    if row is None or row[0] is None:
        return None
    return float(row[0]), float(row[1] or 0.0)


def record_daily_snapshot() -> dict:
    """Capture today's account state. Idempotent — safe to run multiple times a day."""
    account = get_account()
    if account is None:
        log.warning("record_daily_snapshot: broker not connected, skipping")
        return {"status": "no_account"}

    total_value = account["equity"]
    cash = account["cash"]
    positions = get_positions()

    prev = _previous_snapshot()
    if prev is not None:
        prev_value, prev_cumret = prev
        daily_return = (total_value - prev_value) / prev_value if prev_value else 0.0
        cumulative_return = (1 + prev_cumret) * (1 + daily_return) - 1
    else:
        daily_return = 0.0
        cumulative_return = 0.0

    with conn() as c, c.cursor() as cur:
        cur.execute("SELECT MAX(total_value) FROM portfolio_snapshots")
        peak_row = cur.fetchone()
        peak = max(float(peak_row[0]), total_value) if peak_row and peak_row[0] is not None else total_value
        drawdown = (total_value - peak) / peak if peak else 0.0

        cur.execute(
            """
            INSERT INTO portfolio_snapshots
                (date, total_value, cash, positions, daily_return, cumulative_return, drawdown)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (date) DO UPDATE
              SET total_value       = EXCLUDED.total_value,
                  cash              = EXCLUDED.cash,
                  positions         = EXCLUDED.positions,
                  daily_return      = EXCLUDED.daily_return,
                  cumulative_return = EXCLUDED.cumulative_return,
                  drawdown          = EXCLUDED.drawdown
            """,
            (date.today(), total_value, cash, Json(positions), daily_return, cumulative_return, drawdown),
        )
        c.commit()

    log.info(
        "record_daily_snapshot",
        total_value=total_value, daily_return=daily_return, drawdown=drawdown,
    )
    return {"status": "ok", "total_value": total_value, "daily_return": daily_return, "drawdown": drawdown}
