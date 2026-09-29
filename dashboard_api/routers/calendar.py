"""Calendar — SPEC dashboard addendum. Upcoming earnings/FOMC/CPI/jobs reports,
with a click-to-drill-down plan of action for events >= 7 days out.
"""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, HTTPException

from src.core.config import universe
from src.core.db import conn
from .. import event_sources

router = APIRouter(prefix="/api/calendar", tags=["calendar"])


@router.post("/sync")
def sync(days_ahead: int = 60):
    tickers = universe().get("seed_tickers", [])
    return event_sources.sync_events(tickers, days_ahead=days_ahead)


@router.get("/events")
def list_events(days_ahead: int = 60):
    end = date.today() + timedelta(days=days_ahead)
    with conn() as c, c.cursor() as cur:
        cur.execute(
            """
            SELECT id, event_date, event_type, ticker, title, description,
                   plan_of_action, plan_generated_at
            FROM calendar_events
            WHERE event_date BETWEEN %s AND %s
            ORDER BY event_date ASC
            """,
            (date.today(), end),
        )
        rows = cur.fetchall()
    return {
        "events": [
            {
                "id": r[0],
                "event_date": r[1].isoformat(),
                "event_type": r[2],
                "ticker": r[3],
                "title": r[4],
                "description": r[5],
                "days_out": (r[1] - date.today()).days,
                "plan_available": r[6] is not None,
                "plan_eligible": (r[1] - date.today()).days >= 7,
                "plan_generated_at": r[7].isoformat() if r[7] else None,
            }
            for r in rows
        ]
    }


@router.get("/events/{event_id}/plan")
def get_plan(event_id: int, force_refresh: bool = False):
    with conn() as c, c.cursor() as cur:
        cur.execute(
            "SELECT event_date, plan_of_action FROM calendar_events WHERE id = %s",
            (event_id,),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="event not found")
    event_date, cached_plan = row
    days_out = (event_date - date.today()).days
    if days_out < 7 and not cached_plan:
        return {
            "available": False,
            "reason": f"Event is only {days_out} day(s) out — plans are generated for events >= 7 days out.",
        }
    if cached_plan and not force_refresh:
        return {"available": True, "plan": cached_plan, "cached": True}
    plan = event_sources.generate_plan_of_action(event_id)
    return {"available": True, "plan": plan, "cached": False}
