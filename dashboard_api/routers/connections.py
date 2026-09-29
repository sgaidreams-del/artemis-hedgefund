"""Connection monitor — SPEC §11.1 Risk Monitor / Data Health pages, condensed
into a single always-visible status strip per the Robinhood-style "at a glance" requirement.
"""
from __future__ import annotations

import time

from fastapi import APIRouter
import redis as redis_lib

from src.core.config import env
from src.core.db import ping as pg_ping
from .. import alpaca_client, llm

router = APIRouter(prefix="/api/connections", tags=["connections"])


def _redis_ping() -> dict:
    start = time.monotonic()
    try:
        r = redis_lib.Redis(
            host=env("REDIS_HOST", "127.0.0.1"),
            port=int(env("REDIS_PORT", "6379")),
            socket_connect_timeout=2,
        )
        ok = r.ping()
        return {"connected": bool(ok), "reason": None, "latency_ms": round((time.monotonic() - start) * 1000, 1)}
    except Exception as e:
        return {"connected": False, "reason": str(e), "latency_ms": round((time.monotonic() - start) * 1000, 1)}


def _postgres_ping() -> dict:
    start = time.monotonic()
    ok = pg_ping()
    return {
        "connected": ok,
        "reason": None if ok else "connection failed",
        "latency_ms": round((time.monotonic() - start) * 1000, 1),
    }


@router.get("/status")
def status():
    return {
        "alpaca": alpaca_client.ping(),
        "postgres": _postgres_ping(),
        "redis": _redis_ping(),
        "deepseek": {
            "connected": llm.configured(),
            "reason": None if llm.configured() else "DEEPSEEK_API_KEY not set",
            "latency_ms": None,
        },
    }
