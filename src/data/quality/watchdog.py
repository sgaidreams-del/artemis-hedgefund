"""Data quality watchdog. SPEC §4.3."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from psycopg import sql
from psycopg.types.json import Json

from ...core.db import conn
from ...core.logging import get_logger, log_activity

log = get_logger("data_quality")


def _table_freshness(table: str, ts_col: str) -> int:
    """Return age in seconds of most recent row, or -1 if empty."""
    with conn() as c, c.cursor() as cur:
        cur.execute(
            sql.SQL("SELECT MAX({}) FROM {}").format(sql.Identifier(ts_col), sql.Identifier(table))
        )
        row = cur.fetchone()
        if not row or not row[0]:
            return -1
        last = row[0]
        if isinstance(last, datetime):
            return int((datetime.now(timezone.utc) - last).total_seconds())
        # date → compare to today
        return (datetime.now(timezone.utc).date() - last).days * 86400


def run() -> dict:
    """Compute health score 0-100 across data sources."""
    issues: list[dict] = []
    score = 100

    checks = [
        ("ohlcv_daily", "date", 24 * 3600 * 3, 20, "EOD prices stale > 3 days"),
        ("news_headlines", "timestamp", 3600 * 2, 10, "News > 2h old"),
        ("macro_indicators", "date", 86400 * 7, 5, "Macro > 7 days old"),
    ]
    for table, ts_col, max_age_sec, penalty, msg in checks:
        try:
            age = _table_freshness(table, ts_col)
            if age == -1:
                issues.append({"table": table, "issue": "empty", "penalty": penalty})
                score -= penalty
            elif age > max_age_sec:
                issues.append({"table": table, "issue": msg, "age_sec": age, "penalty": penalty})
                score -= penalty
        except Exception as e:
            issues.append({"table": table, "issue": "check_failed", "err": str(e), "penalty": 5})
            score -= 5

    score = max(0, score)
    with conn() as c, c.cursor() as cur:
        cur.execute(
            "INSERT INTO data_quality_reports (timestamp, source, health_score, issues) VALUES (%s, %s, %s, %s)",
            (datetime.now(timezone.utc), "watchdog", score, Json({"issues": issues})),
        )
        c.commit()
    log_activity("data_quality", "run", "ok", score=score, issues=len(issues))
    return {"score": score, "issues": issues}
