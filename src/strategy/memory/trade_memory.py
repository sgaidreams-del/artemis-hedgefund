"""Trade memory — persist trade decisions and deferred reflections."""
from __future__ import annotations

import json
from datetime import date, timedelta

from src.core.db import conn
from src.core.logging import get_logger

log = get_logger("trade_memory")


def log_decision(
    ticker: str,
    action: str,
    entry_price: float,
    signals: dict,
    debate_summary: str,
    regime: str,
) -> int:
    """Insert a new trade decision into trade_memory.

    Returns the auto-generated row id.
    """
    today = date.today()
    with conn() as c, c.cursor() as cur:
        cur.execute(
            """
            INSERT INTO trade_memory
                (ticker, trade_date, action, entry_price, signals, debate_summary, regime, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending')
            RETURNING id
            """,
            (
                ticker,
                today,
                action,
                entry_price,
                json.dumps(signals),
                debate_summary,
                regime,
            ),
        )
        row = cur.fetchone()
        c.commit()

    row_id = int(row[0])
    log.info("log_decision: inserted id=%d ticker=%s action=%s", row_id, ticker, action)
    return row_id


def get_memory(ticker: str, n: int = 5) -> list[dict]:
    """Return the most recent *n* trade_memory rows for *ticker*.

    Rows are returned newest-first.
    """
    with conn() as c, c.cursor() as cur:
        cur.execute(
            """
            SELECT id, ticker, trade_date, action, entry_price,
                   signals, debate_summary, regime, status,
                   actual_return_5d, alpha_vs_spy_5d, reflection, resolved_date
            FROM trade_memory
            WHERE ticker = %s
            ORDER BY trade_date DESC, id DESC
            LIMIT %s
            """,
            (ticker, n),
        )
        rows = cur.fetchall()

    columns = [
        "id", "ticker", "trade_date", "action", "entry_price",
        "signals", "debate_summary", "regime", "status",
        "actual_return_5d", "alpha_vs_spy_5d", "reflection", "resolved_date",
    ]
    return [dict(zip(columns, row)) for row in rows]


def get_pending_reflections(days_old: int = 5) -> list[dict]:
    """Return trade_memory rows that are pending and old enough to have 5-day returns.

    A row is eligible when trade_date <= today - days_old.
    """
    cutoff = date.today() - timedelta(days=days_old)
    with conn() as c, c.cursor() as cur:
        cur.execute(
            """
            SELECT id, ticker, trade_date, action, entry_price,
                   signals, debate_summary, regime, status,
                   actual_return_5d, alpha_vs_spy_5d, reflection, resolved_date
            FROM trade_memory
            WHERE status = 'pending'
              AND trade_date <= %s
            ORDER BY trade_date ASC
            """,
            (cutoff,),
        )
        rows = cur.fetchall()

    columns = [
        "id", "ticker", "trade_date", "action", "entry_price",
        "signals", "debate_summary", "regime", "status",
        "actual_return_5d", "alpha_vs_spy_5d", "reflection", "resolved_date",
    ]
    return [dict(zip(columns, row)) for row in rows]


def update_reflection(
    id: int,
    actual_return: float,
    alpha: float,
    reflection: str,
) -> None:
    """Mark a trade as resolved and record the 5-day return metrics and LLM reflection."""
    today = date.today()
    with conn() as c, c.cursor() as cur:
        cur.execute(
            """
            UPDATE trade_memory
            SET status = 'resolved',
                actual_return_5d = %s,
                alpha_vs_spy_5d = %s,
                reflection = %s,
                resolved_date = %s
            WHERE id = %s
            """,
            (actual_return, alpha, reflection, today, id),
        )
        c.commit()
    log.info("update_reflection: resolved id=%d return=%.4f alpha=%.4f", id, actual_return, alpha)
