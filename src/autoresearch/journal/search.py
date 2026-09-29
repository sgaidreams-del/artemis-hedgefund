"""Research journal search utilities."""
from __future__ import annotations

import json

from src.core.db import conn
from src.core.logging import get_logger

log = get_logger(__name__)


def _deserialize_row(row: tuple, cols: list[str]) -> dict:
    entry = dict(zip(cols, row))
    for field in ("performance", "validation"):
        val = entry.get(field)
        if isinstance(val, str):
            try:
                entry[field] = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                pass
    return entry


def search_by_tags(tags: list[str]) -> list[dict]:
    """SELECT WHERE tags @> %s (GIN index on tags column).

    Assumes a ``tags`` column of type text[] with a GIN index.
    """
    log.info("journal_search_by_tags", tags=tags)

    sql = """
        SELECT
            experiment_id, hypothesis_id, category, description,
            result, performance, validation, learnings, created_at, updated_at
        FROM research_journal
        WHERE tags @> %s
        ORDER BY created_at DESC
    """
    with conn() as c, c.cursor() as cur:
        cur.execute(sql, (tags,))
        rows = cur.fetchall()
        cols = [desc[0] for desc in cur.description]

    return [_deserialize_row(r, cols) for r in rows]


def search_by_date_range(start: str, end: str) -> list[dict]:
    """SELECT WHERE date BETWEEN start AND end.

    start, end should be ISO date strings, e.g. '2025-01-01'.
    """
    log.info("journal_search_by_date_range", start=start, end=end)

    sql = """
        SELECT
            experiment_id, hypothesis_id, category, description,
            result, performance, validation, learnings, created_at, updated_at
        FROM research_journal
        WHERE created_at::date BETWEEN %s AND %s
        ORDER BY created_at DESC
    """
    with conn() as c, c.cursor() as cur:
        cur.execute(sql, (start, end))
        rows = cur.fetchall()
        cols = [desc[0] for desc in cur.description]

    return [_deserialize_row(r, cols) for r in rows]
