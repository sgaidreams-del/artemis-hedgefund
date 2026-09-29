"""Calendar event sources: FOMC/CPI/NFP fixed schedules + earnings (yfinance),
plus the quantitative + LLM-narrated "plan of action" generator for events
>= 7 days out.

FOMC dates are hardcoded from the Federal Reserve's published long-range
schedule — verify against https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
if anything looks off, the Fed occasionally adjusts these.

CPI dates are APPROXIMATE (BLS publishes exact dates ~1yr ahead at
https://www.bls.gov/schedule/news_release/cpi.htm) — flagged as such in the
returned event so the UI can show an "approximate" badge.

NFP (jobs report) is always the first Friday of the month — computed, reliable.
"""
from __future__ import annotations

import calendar
import json
from datetime import date, timedelta
from statistics import mean, pstdev

import yfinance as yf

from src.core.db import conn
from src.core.logging import get_logger
from .llm import narrate

log = get_logger("event_sources")

# Federal Reserve published 2026 FOMC meeting calendar (decision day = 2nd day).
# Source: federalreserve.gov long-range schedule, captured pre-cutoff — re-verify yearly.
FOMC_DATES_2026 = [
    date(2026, 1, 28),
    date(2026, 3, 18),
    date(2026, 4, 29),
    date(2026, 6, 17),
    date(2026, 7, 29),
    date(2026, 9, 16),
    date(2026, 10, 28),
    date(2026, 12, 9),
]

# Approximate — BLS CPI release is typically a Tue/Wed/Thu in the 2nd full week
# of the month. Marked approximate=True; not for precise day-of trading decisions.
CPI_APPROX_DAY_OF_MONTH = 12


def _first_friday(year: int, month: int) -> date:
    first_weekday, _ = calendar.monthrange(year, month)
    # monthrange returns weekday of day 1 (0=Mon..6=Sun)
    days_to_friday = (4 - first_weekday) % 7
    return date(year, month, 1) + timedelta(days=days_to_friday)


def get_fomc_events(start: date, end: date) -> list[dict]:
    return [
        {
            "event_date": d,
            "event_type": "fomc",
            "ticker": None,
            "title": "FOMC Rate Decision",
            "description": "Federal Reserve interest rate decision + press conference.",
            "approximate": False,
        }
        for d in FOMC_DATES_2026
        if start <= d <= end
    ]


def get_nfp_events(start: date, end: date) -> list[dict]:
    events = []
    cur = date(start.year, start.month, 1)
    while cur <= end:
        d = _first_friday(cur.year, cur.month)
        if start <= d <= end:
            events.append({
                "event_date": d,
                "event_type": "jobs_report",
                "ticker": None,
                "title": "Jobs Report (NFP)",
                "description": "BLS Employment Situation report — nonfarm payrolls, unemployment rate.",
                "approximate": False,
            })
        cur = (date(cur.year + (cur.month == 12), (cur.month % 12) + 1, 1))
    return events


def get_cpi_events(start: date, end: date) -> list[dict]:
    events = []
    cur = date(start.year, start.month, 1)
    while cur <= end:
        try:
            d = date(cur.year, cur.month, CPI_APPROX_DAY_OF_MONTH)
        except ValueError:
            cur = date(cur.year + (cur.month == 12), (cur.month % 12) + 1, 1)
            continue
        if start <= d <= end:
            events.append({
                "event_date": d,
                "event_type": "cpi",
                "ticker": None,
                "title": "CPI Release (approximate date)",
                "description": "BLS Consumer Price Index — exact date varies, verify at bls.gov/schedule.",
                "approximate": True,
            })
        cur = date(cur.year + (cur.month == 12), (cur.month % 12) + 1, 1)
    return events


def get_earnings_events(tickers: list[str], start: date, end: date) -> list[dict]:
    events = []
    for ticker in tickers:
        try:
            t = yf.Ticker(ticker)
            edates = t.get_earnings_dates(limit=8)
            if edates is None or edates.empty:
                continue
            for ts, _row in edates.iterrows():
                d = ts.date()
                if start <= d <= end:
                    events.append({
                        "event_date": d,
                        "event_type": "earnings",
                        "ticker": ticker,
                        "title": f"{ticker} Earnings",
                        "description": f"{ticker} quarterly earnings report.",
                        "approximate": False,
                    })
        except Exception as e:
            log.warning("earnings_fetch_failed", ticker=ticker, err=str(e))
    return events


def sync_events(tickers: list[str], days_ahead: int = 60) -> dict:
    """Pull all event sources and upsert into calendar_events. Idempotent."""
    today = date.today()
    end = today + timedelta(days=days_ahead)
    all_events = (
        get_fomc_events(today, end)
        + get_nfp_events(today, end)
        + get_cpi_events(today, end)
        + get_earnings_events(tickers, today, end)
    )
    with conn() as c, c.cursor() as cur:
        for ev in all_events:
            cur.execute(
                """
                INSERT INTO calendar_events (event_date, event_type, ticker, title, description)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (event_date, event_type, (COALESCE(ticker, ''))) DO UPDATE
                  SET title = EXCLUDED.title, description = EXCLUDED.description
                """,
                (ev["event_date"], ev["event_type"], ev["ticker"], ev["title"], ev["description"]),
            )
        c.commit()
    return {"synced": len(all_events)}


def _historical_reaction_stats(ticker: str, event_dates: list[date]) -> dict:
    """Next-day return stats around past occurrences of this event type, from ohlcv_daily.
    Honest about sparse data — never fabricates a stat from < 3 observations.
    """
    if not event_dates:
        return {"n": 0, "note": "no historical event dates available"}
    moves = []
    with conn() as c, c.cursor() as cur:
        for d in event_dates:
            cur.execute(
                """
                SELECT date, close FROM ohlcv_daily
                WHERE ticker = %s AND date BETWEEN %s AND %s
                ORDER BY date
                """,
                (ticker, d - timedelta(days=5), d + timedelta(days=5)),
            )
            rows = cur.fetchall()
            before = [r for r in rows if r[0] <= d]
            after = [r for r in rows if r[0] > d]
            if before and after:
                pre_close = float(before[-1][1])
                post_close = float(after[0][1])
                if pre_close:
                    moves.append((post_close - pre_close) / pre_close)
    n = len(moves)
    if n < 3:
        return {"n": n, "note": "insufficient historical data — improves as more price history is backfilled"}
    return {
        "n": n,
        "avg_move_pct": round(mean(moves) * 100, 2),
        "std_move_pct": round(pstdev(moves) * 100, 2) if n > 1 else 0.0,
        "max_move_pct": round(max(moves, key=abs) * 100, 2),
    }


def generate_plan_of_action(event_id: int) -> dict:
    """Compute quant stats + DeepSeek narrative for one event. Caches to calendar_events."""
    with conn() as c, c.cursor() as cur:
        cur.execute(
            "SELECT event_date, event_type, ticker, title, description FROM calendar_events WHERE id = %s",
            (event_id,),
        )
        row = cur.fetchone()
        if not row:
            return {"error": "event not found"}
        event_date, event_type, ticker, title, description = row

        reaction_ticker = ticker or "SPY"
        # Reference past occurrences: prior FOMC dates / prior month NFP-CPI days /
        # prior earnings dates for this ticker — reuse the same generators, looking back.
        lookback_start = event_date - timedelta(days=730)
        if event_type == "fomc":
            past = [d["event_date"] for d in get_fomc_events(lookback_start, event_date - timedelta(days=1))]
        elif event_type == "jobs_report":
            past = [d["event_date"] for d in get_nfp_events(lookback_start, event_date - timedelta(days=1))]
        elif event_type == "cpi":
            past = [d["event_date"] for d in get_cpi_events(lookback_start, event_date - timedelta(days=1))]
        elif event_type == "earnings" and ticker:
            past = [d["event_date"] for d in get_earnings_events([ticker], lookback_start, event_date - timedelta(days=1))]
        else:
            past = []

        stats = _historical_reaction_stats(reaction_ticker, past)

        days_out = (event_date - date.today()).days
        narrative = narrate(
            system_prompt=(
                "You are a concise markets analyst producing a brief pre-event plan of action "
                "for a personal trading system. Be specific and actionable, but never assert "
                "precise numeric predictions beyond what the provided historical stats support. "
                "If historical data is insufficient, give qualitative positioning considerations "
                "instead (e.g. position sizing, watch-list items, what would change the thesis)."
            ),
            user_prompt=(
                f"Event: {title}\n"
                f"Type: {event_type}\n"
                f"Date: {event_date.isoformat()} ({days_out} days out)\n"
                f"Description: {description}\n"
                f"Relevant ticker for reaction stats: {reaction_ticker}\n"
                f"Historical reaction stats (N={stats['n']}): {stats}\n\n"
                "Write a 3-5 sentence plan of action: what to watch for, how this system "
                "should think about position sizing/risk around this date, and what would "
                "change the read on it."
            ),
        )

        plan = {
            "quant_stats": stats,
            "narrative": narrative or "DeepSeek unavailable — quantitative stats only.",
            "reaction_ticker": reaction_ticker,
        }
        cur.execute(
            "UPDATE calendar_events SET plan_of_action = %s, plan_generated_at = now() WHERE id = %s",
            (json.dumps(plan), event_id),
        )
        c.commit()
        return plan
