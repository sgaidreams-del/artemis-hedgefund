"""Promotion pipeline — manages shadow → paper → live stage progression."""
from __future__ import annotations

import json
from enum import Enum

from src.core.db import conn
from src.core.logging import get_logger

log = get_logger(__name__)


class PromotionStage(Enum):
    SHADOW = "shadow"
    PAPER = "paper"
    LIVE = "live"


_STAGE_ORDER = [PromotionStage.SHADOW, PromotionStage.PAPER, PromotionStage.LIVE]


def _get_deployment(experiment_id: str) -> dict:
    """Fetch deployment JSON for an experiment from the journal."""
    sql = """
        SELECT performance, validation, result
        FROM research_journal
        WHERE experiment_id = %s
    """
    with conn() as c, c.cursor() as cur:
        cur.execute(sql, (experiment_id,))
        row = cur.fetchone()

    if row is None:
        return {}

    performance, validation, result = row
    if isinstance(performance, str):
        try:
            performance = json.loads(performance)
        except (json.JSONDecodeError, TypeError):
            performance = {}
    if isinstance(validation, str):
        try:
            validation = json.loads(validation)
        except (json.JSONDecodeError, TypeError):
            validation = {}

    return {
        "performance": performance or {},
        "validation": validation or {},
        "result": result,
    }


def _get_deployment_field(experiment_id: str) -> dict:
    """Fetch the ``deployment`` JSON column (stage tracking metadata)."""
    sql = """
        SELECT deployment
        FROM research_journal
        WHERE experiment_id = %s
    """
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


def _update_deployment_field(experiment_id: str, deployment: dict) -> None:
    """Write deployment metadata back to the journal."""
    sql = """
        UPDATE research_journal
        SET deployment = %s
        WHERE experiment_id = %s
    """
    with conn() as c, c.cursor() as cur:
        cur.execute(sql, (json.dumps(deployment), experiment_id))


def check_promotion_ready(experiment_id: str) -> bool:
    """Return True if experiment is ready for promotion.

    Criteria: shadow_days >= 30 AND paper_sharpe > 0.5.
    """
    deployment = _get_deployment_field(experiment_id)
    shadow_days = deployment.get("shadow_days", 0)
    paper_sharpe = deployment.get("paper_sharpe", 0.0)

    ready = shadow_days >= 30 and paper_sharpe > 0.5
    log.info(
        "check_promotion_ready",
        experiment_id=experiment_id,
        shadow_days=shadow_days,
        paper_sharpe=paper_sharpe,
        ready=ready,
    )
    return ready


def promote(experiment_id: str) -> str:
    """Advance experiment to the next promotion stage.

    Returns the new stage name string.
    """
    deployment = _get_deployment_field(experiment_id)
    current_stage_name = deployment.get("stage", PromotionStage.SHADOW.value)

    try:
        current_stage = PromotionStage(current_stage_name)
    except ValueError:
        current_stage = PromotionStage.SHADOW

    current_idx = _STAGE_ORDER.index(current_stage)
    if current_idx < len(_STAGE_ORDER) - 1:
        new_stage = _STAGE_ORDER[current_idx + 1]
    else:
        log.info("promote_already_live", experiment_id=experiment_id)
        return current_stage.value

    deployment["stage"] = new_stage.value
    deployment["previous_stage"] = current_stage.value
    _update_deployment_field(experiment_id, deployment)

    log.info(
        "promote",
        experiment_id=experiment_id,
        from_stage=current_stage.value,
        to_stage=new_stage.value,
    )
    return new_stage.value
