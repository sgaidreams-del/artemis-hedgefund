"""Activity feed — reads logs/activity.jsonl written by src.core.logging.log_activity.

Read-only visibility into safeguard events (risk halts, reconciliation
mismatches) that don't otherwise surface anywhere a human would see them —
the kill switch table only carries the *current* reason, not history, and
reconciliation findings that don't trigger a kill-switch engage are
otherwise invisible outside the raw log file.
"""
from __future__ import annotations

import json
import logging
from collections import deque

from fastapi import APIRouter

from src.core.logging import ACTIVITY_LOG

router = APIRouter(prefix="/api/activity", tags=["activity"])
log = logging.getLogger(__name__)

ALERT_STATUSES = {"alert", "halt"}


@router.get("")
def list_activity(limit: int = 100):
    if not ACTIVITY_LOG.exists():
        return {"entries": [], "empty_reason": "No activity logged yet."}

    try:
        with ACTIVITY_LOG.open() as f:
            lines = deque(f, maxlen=limit)
    except Exception as exc:
        log.exception("list_activity: failed to read activity log")
        return {"error": str(exc), "entries": []}

    entries = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    entries.reverse()
    return {
        "entries": entries,
        "empty_reason": None if entries else "No activity logged yet.",
    }
