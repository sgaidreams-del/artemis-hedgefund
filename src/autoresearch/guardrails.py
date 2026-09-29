"""Guardrails — safety checks before running new experiments."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.core.db import conn
from src.core.logging import get_logger

log = get_logger(__name__)

MAX_EXPERIMENTS_PER_WEEK = 20


def _count_experiments_this_week() -> int:
    """Count experiments created in the last 7 days."""
    since = datetime.now(timezone.utc) - timedelta(days=7)
    sql = """
        SELECT COUNT(*)
        FROM research_journal
        WHERE created_at >= %s
    """
    with conn() as c, c.cursor() as cur:
        cur.execute(sql, (since,))
        row = cur.fetchone()
    return int(row[0]) if row else 0


def _has_concurrent_live_changes() -> bool:
    """Return True if any experiment is currently in 'live' stage deployment."""
    sql = """
        SELECT COUNT(*)
        FROM research_journal
        WHERE deployment->>'stage' = 'live'
          AND result NOT IN ('ROLLBACK', 'ABANDONED')
    """
    try:
        with conn() as c, c.cursor() as cur:
            cur.execute(sql)
            row = cur.fetchone()
        count = int(row[0]) if row else 0
        # Allow up to 1 live experiment; flag as concurrent if > 1
        return count > 1
    except Exception as exc:
        log.warning("guardrail_live_check_error", error=str(exc))
        return False


def check_guardrails() -> bool:
    """Check: experiments this week < 20, no concurrent live changes.

    Returns True if safe to proceed, False if a guardrail is breached.
    """
    weekly_count = _count_experiments_this_week()
    if weekly_count >= MAX_EXPERIMENTS_PER_WEEK:
        log.warning(
            "guardrail_weekly_limit",
            count=weekly_count,
            limit=MAX_EXPERIMENTS_PER_WEEK,
        )
        return False

    concurrent_live = _has_concurrent_live_changes()
    if concurrent_live:
        log.warning("guardrail_concurrent_live")
        return False

    log.info("guardrails_ok", weekly_count=weekly_count)
    return True
