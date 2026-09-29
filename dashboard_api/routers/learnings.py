"""Learnings tab — SPEC §6.5 Trade Decision Memory. What went wrong, what was
learned, surfaced for human review. Feeds the continuous-improvement loop:
resolved reflections here are exactly what AutoResearch's hypothesis generator
reads first (SPEC §10.2) once that layer ships.
"""
from __future__ import annotations

from fastapi import APIRouter

from src.core.db import conn

router = APIRouter(prefix="/api/learnings", tags=["learnings"])


@router.get("")
def list_learnings(limit: int = 100):
    with conn() as c, c.cursor() as cur:
        cur.execute(
            """
            SELECT id, ticker, trade_date, action, entry_price, regime, status,
                   actual_return_5d, alpha_vs_spy_5d, reflection, resolved_date, label
            FROM trade_memory
            ORDER BY trade_date DESC
            LIMIT %s
            """,
            (limit,),
        )
        rows = cur.fetchall()
    return {
        "learnings": [
            {
                "id": r[0],
                "ticker": r[1],
                "trade_date": r[2].isoformat(),
                "action": r[3],
                "entry_price": float(r[4]) if r[4] is not None else None,
                "regime": r[5],
                "status": r[6],
                "actual_return_5d": float(r[7]) if r[7] is not None else None,
                "alpha_vs_spy_5d": float(r[8]) if r[8] is not None else None,
                "reflection": r[9],
                "resolved_date": r[10].isoformat() if r[10] else None,
                "label": r[11],
            }
            for r in rows
        ],
        "empty_reason": None if rows else "No learnings yet — trade decision memory (SPEC §6.5) "
                                            "populates once the strategy/debate layers ship and trades "
                                            "start resolving 5 trading days later.",
    }
