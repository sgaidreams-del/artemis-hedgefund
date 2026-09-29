"""Artemis dashboard API. Run with:
    uvicorn dashboard_api.main:app --reload --port 8000
"""
from __future__ import annotations

import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .routers import (
    calendar,
    connections,
    learnings,
    portfolio,
    trades,
)
from .routers import activity, analytics, kill_switch, regime, alerts, news, options, trading, sim

app = FastAPI(title="Artemis Dashboard API", version="0.1.0")


def _csv_env(key: str) -> list[str]:
    return [v.strip() for v in os.environ.get(key, "").split(",") if v.strip()]


ALLOWED_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173", *_csv_env("ARTEMIS_ALLOWED_ORIGINS")]
ALLOWED_HOSTS = ["localhost", "127.0.0.1", *_csv_env("ARTEMIS_ALLOWED_HOSTS")]
CLIENT_HEADER = "x-artemis-client"
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@app.middleware("http")
async def _reject_cross_site_writes(request: Request, call_next):
    """CSRF guard for state-changing endpoints (rebalance, straddles, kill switch...).

    CORS alone doesn't stop a malicious page from *sending* a body-less POST
    to localhost — it only hides the response. Requiring a custom header forces
    a CORS preflight, which fails for any origin not in ALLOWED_ORIGINS, and the
    explicit Origin check covers clients that do send one.
    """
    if request.method not in _SAFE_METHODS:
        origin = request.headers.get("origin")
        if origin is not None and origin not in ALLOWED_ORIGINS:
            return JSONResponse({"error": "cross-origin write rejected"}, status_code=403)
        if request.headers.get(CLIENT_HEADER) != "dashboard":
            return JSONResponse(
                {"error": f"missing '{CLIENT_HEADER}: dashboard' header"}, status_code=403
            )
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", CLIENT_HEADER],
)
# Rejects requests whose Host header isn't local — blocks DNS-rebinding
# attacks that would otherwise let a website read portfolio data.
app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)

app.include_router(portfolio.router)
app.include_router(connections.router)
app.include_router(trades.router)
app.include_router(learnings.router)
app.include_router(calendar.router)
app.include_router(analytics.router)
app.include_router(kill_switch.router)
app.include_router(regime.router)
app.include_router(alerts.router)
app.include_router(news.router)
app.include_router(options.router)
app.include_router(trading.router)
app.include_router(activity.router)
app.include_router(sim.router)


@app.on_event("startup")
def _init_kill_switch():
    """Ensure the kill_switch sentinel row exists at startup."""
    from .routers.kill_switch import is_paused
    is_paused()


@app.get("/api/health")
def health():
    return {"status": "ok"}
