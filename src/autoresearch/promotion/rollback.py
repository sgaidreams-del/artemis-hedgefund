"""Rollback — reverts experiments to a prior promotion stage."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from src.core.db import conn
from src.core.logging import get_logger

log = get_logger(__name__)


def _get_deployment_field(experiment_id: str) -> dict:
    sql = "SELECT deployment FROM research_journal WHERE experiment_id = %s"
    try:
        with conn() as c, c.cursor() as cur:
            cur.execute(sql, (experiment_id,))
            row = cur.fetchone()
        if row is None or row[0] is None:
            return {}
        val = row[0]
        if isinstance(val, str):
            return json.loads(val)
        return val
    except Exception:
        return {}


def _update_deployment_and_learnings(
    experiment_id: str, deployment: dict, learnings_append: str
) -> None:
    sql = """
        UPDATE research_journal
        SET
            deployment = %s,
            learnings  = COALESCE(learnings, '') || %s,
            updated_at = %s
        WHERE experiment_id = %s
    """
    with conn() as c, c.cursor() as cur:
        cur.execute(
            sql,
            (json.dumps(deployment), learnings_append, datetime.now(timezone.utc), experiment_id),
        )


def check_rollback(experiment_id: str) -> bool:
    """Return True if paper Sharpe has dropped more than 0.30 since promotion."""
    deployment = _get_deployment_field(experiment_id)
    promotion_sharpe = deployment.get("promotion_sharpe")
    current_sharpe = deployment.get("paper_sharpe")

    if promotion_sharpe is None or current_sharpe is None:
        return False

    drop = float(promotion_sharpe) - float(current_sharpe)
    should_rollback = drop > 0.30

    log.info(
        "check_rollback",
        experiment_id=experiment_id,
        promotion_sharpe=promotion_sharpe,
        current_sharpe=current_sharpe,
        drop=round(drop, 4),
        should_rollback=should_rollback,
    )
    return should_rollback


def rollback(experiment_id: str) -> None:
    """Revert experiment to previous stage and log the rollback in the journal."""
    deployment = _get_deployment_field(experiment_id)

    current_stage = deployment.get("stage", "unknown")
    previous_stage = deployment.get("previous_stage", "shadow")

    deployment["stage"] = previous_stage
    deployment["previous_stage"] = current_stage
    deployment["rollback_at"] = datetime.now(timezone.utc).isoformat()

    note = (
        f"\n[ROLLBACK {datetime.now(timezone.utc).date()}] "
        f"Reverted from {current_stage} to {previous_stage}."
    )
    _update_deployment_and_learnings(experiment_id, deployment, note)

    log.warning(
        "rollback",
        experiment_id=experiment_id,
        from_stage=current_stage,
        to_stage=previous_stage,
    )
