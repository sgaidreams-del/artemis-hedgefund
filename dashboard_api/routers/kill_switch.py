"""Kill-switch — gates all order execution. SPEC §11.1 Risk Controls."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from src.core.db import conn

router = APIRouter(prefix="/api/kill-switch", tags=["kill-switch"])
log = logging.getLogger(__name__)


def engage(reason: str) -> None:
    """Pause new orders AND cancel resting ones. The plain-Python entry point
    used by every halt (Phase 3 loss limits, Phase 4 reconciliation) as well
    as the manual /pause endpoint below — engaging the kill switch should
    always stop the bleeding, not just block what hasn't been submitted yet.
    """
    try:
        with conn() as c, c.cursor() as cur:
            cur.execute(
                "INSERT INTO kill_switch (id, paused) VALUES (1, FALSE) "
                "ON CONFLICT (id) DO NOTHING"
            )
            cur.execute(
                "UPDATE kill_switch SET paused = TRUE, set_at = NOW(), reason = %s "
                "WHERE id = 1",
                (reason,),
            )
    except Exception:
        log.exception("engage: failed to set paused flag — attempting cancel anyway")

    from src.execution.broker import cancel_all_orders

    cancelled = cancel_all_orders()
    log.warning(f"kill switch engaged: {reason} — cancelled {cancelled} resting order(s)")


def is_paused() -> bool:
    """Called by the execution layer before every order submission."""
    try:
        with conn() as c, c.cursor() as cur:
            cur.execute(
                "INSERT INTO kill_switch (id, paused) VALUES (1, FALSE) "
                "ON CONFLICT (id) DO NOTHING"
            )
            cur.execute("SELECT paused FROM kill_switch WHERE id = 1")
            row = cur.fetchone()
            return bool(row[0]) if row else False
    except Exception:
        log.exception("is_paused DB error — defaulting to False")
        return False


def _read_row() -> dict:
    with conn() as c, c.cursor() as cur:
        cur.execute(
            "INSERT INTO kill_switch (id, paused) VALUES (1, FALSE) "
            "ON CONFLICT (id) DO NOTHING"
        )
        cur.execute(
            "SELECT paused, set_at, reason FROM kill_switch WHERE id = 1"
        )
        row = cur.fetchone()
    if row is None:
        return {"paused": False, "set_at": None, "reason": None}
    return {
        "paused": bool(row[0]),
        "set_at": row[1].isoformat() if row[1] else None,
        "reason": row[2],
    }


@router.get("")
def get_status():
    try:
        return _read_row()
    except Exception as exc:
        log.exception("kill-switch GET failed")
        return {"paused": False, "set_at": None, "reason": None, "error": str(exc)}


class PauseBody(BaseModel):
    reason: Optional[str] = None


@router.post("/pause")
def pause(body: PauseBody = PauseBody()):
    try:
        engage(body.reason or "manual pause")
        return _read_row()
    except Exception as exc:
        log.exception("kill-switch pause failed")
        return {"error": str(exc)}


@router.post("/resume")
def resume():
    try:
        with conn() as c, c.cursor() as cur:
            cur.execute(
                "UPDATE kill_switch SET paused = FALSE, set_at = NOW(), reason = NULL "
                "WHERE id = 1"
            )
        return _read_row()
    except Exception as exc:
        log.exception("kill-switch resume failed")
        return {"error": str(exc)}
