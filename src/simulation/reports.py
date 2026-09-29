"""Weekly performance report generator for the trade simulator.

Aggregates sim_snapshots and sim_trades for a given week into sim_weekly_reports.
Called automatically every Friday by run_sim_step(); also available via the
dashboard API for on-demand regeneration.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

from ..core.db import conn
from ..core.logging import get_logger

log = get_logger("sim_reports")


def _annualized_sharpe(daily_returns: list[float]) -> float | None:
    n = len(daily_returns)
    if n < 2:
        return None
    mean_r = sum(daily_returns) / n
    variance = sum((r - mean_r) ** 2 for r in daily_returns) / (n - 1)
    std_r = math.sqrt(variance)
    if std_r == 0:
        return None
    return round(mean_r / std_r * math.sqrt(252), 4)


def generate_weekly_report(week_ending: date | None = None) -> dict:
    """Compute and upsert the weekly report for the 7-day window ending on week_ending."""
    if week_ending is None:
        week_ending = date.today()
    week_starting = week_ending - timedelta(days=6)

    with conn() as c, c.cursor() as cur:
        # Starting value — first snapshot in window (or nearest prior)
        cur.execute(
            "SELECT total_value FROM sim_snapshots "
            "WHERE date >= %s AND date <= %s ORDER BY date ASC LIMIT 1",
            (week_starting, week_ending),
        )
        row = cur.fetchone()
        if row is None:
            return {"status": "no_data", "week_ending": week_ending.isoformat()}
        starting_value = float(row[0])

        # Ending value
        cur.execute(
            "SELECT total_value FROM sim_snapshots WHERE date <= %s ORDER BY date DESC LIMIT 1",
            (week_ending,),
        )
        row = cur.fetchone()
        ending_value = float(row[0]) if row else starting_value

        # Max drawdown for the week
        cur.execute(
            "SELECT MIN(drawdown) FROM sim_snapshots WHERE date >= %s AND date <= %s",
            (week_starting, week_ending),
        )
        row = cur.fetchone()
        max_drawdown_pct = float(row[0]) * 100.0 if row and row[0] is not None else 0.0

        # Sharpe from daily returns in the window
        cur.execute(
            "SELECT daily_return FROM sim_snapshots "
            "WHERE date >= %s AND date <= %s AND daily_return IS NOT NULL",
            (week_starting, week_ending),
        )
        daily_returns = [float(r[0]) for r in cur.fetchall()]
        sharpe_weekly = _annualized_sharpe(daily_returns)

        # Total return vs starting capital
        cur.execute("SELECT starting_capital FROM sim_config WHERE id = 1")
        cfg = cur.fetchone()
        sc = float(cfg[0]) if cfg else 100_000.0
        weekly_return_pct = ((ending_value - starting_value) / starting_value * 100.0) if starting_value > 0 else 0.0
        total_return_pct = ((ending_value - sc) / sc * 100.0) if sc > 0 else 0.0

        # Closed trade stats for the week
        cur.execute(
            "SELECT realized_pnl FROM sim_trades "
            "WHERE side = 'sell' AND date >= %s AND date <= %s AND realized_pnl IS NOT NULL",
            (week_starting, week_ending),
        )
        pnls = [float(r[0]) for r in cur.fetchall()]
        total_trades = len(pnls)
        winning_trades = sum(1 for p in pnls if p > 0)
        losing_trades = sum(1 for p in pnls if p <= 0)
        win_rate_pct = (winning_trades / total_trades * 100.0) if total_trades > 0 else 0.0
        gross_profit = sum(p for p in pnls if p > 0)
        gross_loss = abs(sum(p for p in pnls if p < 0))
        avg_win = (gross_profit / winning_trades) if winning_trades > 0 else 0.0
        avg_loss = (gross_loss / losing_trades) if losing_trades > 0 else 0.0
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else None

        cur.execute(
            """
            INSERT INTO sim_weekly_reports
                (week_ending, starting_value, ending_value, weekly_return_pct,
                 total_return_pct, max_drawdown_pct, sharpe_weekly,
                 total_trades, winning_trades, losing_trades, win_rate_pct,
                 avg_win, avg_loss, profit_factor, gross_profit, gross_loss)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (week_ending) DO UPDATE
              SET starting_value    = EXCLUDED.starting_value,
                  ending_value      = EXCLUDED.ending_value,
                  weekly_return_pct = EXCLUDED.weekly_return_pct,
                  total_return_pct  = EXCLUDED.total_return_pct,
                  max_drawdown_pct  = EXCLUDED.max_drawdown_pct,
                  sharpe_weekly     = EXCLUDED.sharpe_weekly,
                  total_trades      = EXCLUDED.total_trades,
                  winning_trades    = EXCLUDED.winning_trades,
                  losing_trades     = EXCLUDED.losing_trades,
                  win_rate_pct      = EXCLUDED.win_rate_pct,
                  avg_win           = EXCLUDED.avg_win,
                  avg_loss          = EXCLUDED.avg_loss,
                  profit_factor     = EXCLUDED.profit_factor,
                  gross_profit      = EXCLUDED.gross_profit,
                  gross_loss        = EXCLUDED.gross_loss,
                  created_at        = NOW()
            """,
            (week_ending, starting_value, ending_value, weekly_return_pct,
             total_return_pct, max_drawdown_pct, sharpe_weekly,
             total_trades, winning_trades, losing_trades, win_rate_pct,
             avg_win, avg_loss, profit_factor, gross_profit, gross_loss),
        )
        c.commit()

    log.info("generate_weekly_report", week_ending=week_ending.isoformat(),
             weekly_return_pct=round(weekly_return_pct, 4))

    return {
        "week_ending": week_ending.isoformat(),
        "starting_value": starting_value,
        "ending_value": ending_value,
        "weekly_return_pct": round(weekly_return_pct, 4),
        "total_return_pct": round(total_return_pct, 4),
        "max_drawdown_pct": round(max_drawdown_pct, 4),
        "sharpe_weekly": sharpe_weekly,
        "total_trades": total_trades,
        "winning_trades": winning_trades,
        "losing_trades": losing_trades,
        "win_rate_pct": round(win_rate_pct, 4),
        "gross_profit": round(gross_profit, 4),
        "gross_loss": round(gross_loss, 4),
        "profit_factor": round(profit_factor, 4) if profit_factor else None,
    }
