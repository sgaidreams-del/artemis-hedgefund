"""Structured logging — writes both stdout and activity.jsonl."""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import structlog

ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
ACTIVITY_LOG = LOG_DIR / "activity.jsonl"


def configure(level: str = "INFO") -> None:
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
    )
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
    )


def log_activity(component: str, action: str, status: str = "ok", **kwargs) -> None:
    """Append a JSON line to logs/activity.jsonl for daily report aggregation."""
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "component": component,
        "action": action,
        "status": status,
        **kwargs,
    }
    with ACTIVITY_LOG.open("a") as f:
        f.write(json.dumps(record) + "\n")


def get_logger(name: str) -> structlog.BoundLogger:
    return structlog.get_logger(name)
