"""Research journal CRUD operations."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from src.core.db import conn
from src.core.logging import get_logger

log = get_logger(__name__)


def create_entry(
    experiment_id: str,
    hypothesis_id: str,
    category: str,
    description: str,
) -> str:
    """INSERT a new row into research_journal. Returns experiment_id."""
    log.info("journal_create_entry", experiment_id=experiment_id, hypothesis_id=hypothesis_id)

    sql = """
        INSERT INTO research_journal
            (experiment_id, hypothesis_id, category, description, created_at)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (experiment_id) DO NOTHING
    """
    with conn() as c, c.cursor() as cur:
        cur.execute(
            sql,
            (
                experiment_id,
                hypothesis_id,
                category,
                description,
                datetime.now(timezone.utc),
            ),
        )
    return experiment_id


def update_entry(
    experiment_id: str,
    result: str,
    performance: dict,
    validation: dict,
    learnings: str,
) -> None:
    """UPDATE research_journal SET result, performance, validation, learnings WHERE experiment_id."""
    log.info("journal_update_entry", experiment_id=experiment_id, result=result)

    sql = """
        UPDATE research_journal
        SET
            result      = %s,
            performance = %s,
            validation  = %s,
            learnings   = %s,
            updated_at  = %s
        WHERE experiment_id = %s
    """
    with conn() as c, c.cursor() as cur:
        cur.execute(
            sql,
            (
                result,
                json.dumps(performance),
                json.dumps(validation),
                learnings,
                datetime.now(timezone.utc),
                experiment_id,
            ),
        )


def get_recent(n: int = 20) -> list[dict]:
    """SELECT n most recent research_journal rows. Returns list of dicts."""
    sql = """
        SELECT
            experiment_id,
            hypothesis_id,
            category,
            description,
            result,
            performance,
            validation,
            learnings,
            created_at,
            updated_at
        FROM research_journal
        ORDER BY created_at DESC
        LIMIT %s
    """
    with conn() as c, c.cursor() as cur:
        cur.execute(sql, (n,))
        rows = cur.fetchall()
        cols = [desc[0] for desc in cur.description]

    entries = []
    for row in rows:
        entry = dict(zip(cols, row))
        # Deserialize JSONB columns if they come back as strings
        for field in ("performance", "validation"):
            val = entry.get(field)
            if isinstance(val, str):
                try:
                    entry[field] = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    pass
        entries.append(entry)

    return entries
