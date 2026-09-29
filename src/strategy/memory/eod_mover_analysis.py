"""End-of-day biggest-mover analysis.

After market close, identifies the day's top price movers from the seed universe
and — for any ticker not traded that day — generates a DeepSeek post-mortem on
what signals were available but not acted on. Inserted into trade_memory with
label='Missed' so they surface in the Learnings tab and feed AutoResearch.
"""
from __future__ import annotations

import os
from datetime import date
from typing import Optional

from openai import OpenAI
from psycopg.types.json import Jsonb

from src.core.config import universe as universe_cfg
from src.core.db import conn
from src.core.logging import get_logger, log_activity

log = get_logger("eod_mover_analysis")

MIN_MOVE_PCT = 2.0         # flag moves with abs daily change >= 2%
TOP_N = 5                  # max movers to analyze per day (seed universe)
TOP_N_EXTENDED = 3         # max Universe Miss entries per day (extended watchlist)

_UNIVERSE_MISS_PROMPT = """\
You are a quantitative analyst reviewing an end-of-day market miss for a systematic trading strategy.

Context:
- Date: {date}
- Ticker: {ticker} (NOT currently in the active trading universe)
- Sector: {sector}
- Actual daily move: {pct_change:+.2f}%
- Volume today: {volume_today:,}
- 20-day avg volume (approx): {volume_avg:,}
- Volume ratio: {volume_ratio:.1f}x normal

This ticker is NOT in our trading universe — we had zero exposure or analysis for it.

Write a concise (3-4 sentence) analysis covering:
1. What type of catalyst most likely caused this move (binary event, earnings, momentum, macro).
2. What publicly observable pre-move markers (unusual volume, IV spike, options sweep, catalyst calendar) would have flagged this in the days before the move.
3. Whether this ticker should be added to the active trading universe, and what signal infrastructure it would need.

Be specific. Reference the volume ratio and move magnitude quantitatively.
"""

_PROMPT = """\
You are a quantitative analyst reviewing end-of-day performance for a systematic trading strategy.

Context:
- Date: {date}
- Regime: {regime}
- Ticker: {ticker}
- Actual daily move: {pct_change:+.2f}%
- Had an existing position before open: {had_position}

Available signals on this date:
{signals_summary}

Ensemble model output:
- Final score: {final_score:.4f}
- Target weight: {target_weight:.4f}
- Component scores: {component_scores}

No trade was executed on this ticker today despite a {pct_change:+.2f}% move.

Write a concise (3-4 sentence) analysis covering:
1. Whether the available signals contained a detectable edge for this move.
2. Which specific signal(s) were most informative or most misleading in hindsight.
3. One concrete, actionable improvement to signal weights or thresholds that would have triggered action.

Be specific and quantitative. Avoid generic statements.
"""


def _client() -> OpenAI:
    return OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com")


def _latest_trade_date() -> Optional[date]:
    with conn() as c, c.cursor() as cur:
        cur.execute("SELECT MAX(date) FROM ohlcv_daily")
        return cur.fetchone()[0]


def _get_movers(trade_date: date, tickers: list[str]) -> list[dict]:
    """Top movers by abs % change on trade_date, filtered to seed universe."""
    with conn() as c, c.cursor() as cur:
        cur.execute(
            """
            SELECT t.ticker,
                   t.close,
                   p.close                                    AS prev_close,
                   (t.close - p.close) / p.close * 100       AS pct_change
            FROM   ohlcv_daily t
            JOIN   ohlcv_daily p
                     ON  p.ticker = t.ticker
                     AND p.date   = (
                           SELECT MAX(date) FROM ohlcv_daily
                           WHERE  ticker = t.ticker AND date < %s
                     )
            WHERE  t.date    = %s
              AND  t.ticker  = ANY(%s)
              AND  ABS((t.close - p.close) / p.close * 100) >= %s
            ORDER  BY ABS((t.close - p.close) / p.close * 100) DESC
            LIMIT  %s
            """,
            (trade_date, trade_date, tickers, MIN_MOVE_PCT, TOP_N),
        )
        return [
            {
                "ticker": r[0],
                "close": float(r[1]),
                "prev_close": float(r[2]),
                "pct_change": float(r[3]),
            }
            for r in cur.fetchall()
        ]


def _spy_daily_return(trade_date: date) -> Optional[float]:
    with conn() as c, c.cursor() as cur:
        cur.execute(
            """
            SELECT (t.close - p.close) / p.close
            FROM   ohlcv_daily t
            JOIN   ohlcv_daily p
                     ON  p.ticker = 'SPY'
                     AND p.date   = (SELECT MAX(date) FROM ohlcv_daily WHERE ticker='SPY' AND date < %s)
            WHERE  t.ticker = 'SPY' AND t.date = %s
            """,
            (trade_date, trade_date),
        )
        row = cur.fetchone()
        return float(row[0]) if row else None


def _was_traded(ticker: str, trade_date: date) -> bool:
    with conn() as c, c.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM submitted_orders WHERE symbol = %s AND submitted_at::date = %s LIMIT 1",
            (ticker, trade_date),
        )
        return cur.fetchone() is not None


def _already_analyzed(ticker: str, trade_date: date) -> bool:
    with conn() as c, c.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM trade_memory WHERE ticker=%s AND trade_date=%s AND label='Missed' LIMIT 1",
            (ticker, trade_date),
        )
        return cur.fetchone() is not None


def _get_signals(ticker: str, trade_date: date) -> dict:
    with conn() as c, c.cursor() as cur:
        cur.execute(
            "SELECT signal_name, value, confidence FROM signals WHERE ticker=%s AND date=%s",
            (ticker, trade_date),
        )
        return {r[0]: {"value": float(r[1]), "confidence": float(r[2])} for r in cur.fetchall()}


def _get_ensemble(ticker: str, trade_date: date) -> Optional[dict]:
    with conn() as c, c.cursor() as cur:
        cur.execute(
            "SELECT final_score, target_weight, regime, component_scores FROM ensemble_scores WHERE ticker=%s AND date=%s",
            (ticker, trade_date),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "final_score": float(row[0]),
            "target_weight": float(row[1]),
            "regime": row[2],
            "component_scores": row[3],
        }


def _has_position(ticker: str) -> bool:
    """True if ticker appears in the fills table (rough: at least one buy recorded)."""
    with conn() as c, c.cursor() as cur:
        cur.execute("SELECT 1 FROM trades WHERE ticker=%s LIMIT 1", (ticker,))
        return cur.fetchone() is not None


def _format_signals(signals: dict) -> str:
    if not signals:
        return "  (no signals recorded for this date)"
    return "\n".join(
        f"  {name}: {v['value']:+.4f} (conf {v['confidence']:.2f})"
        for name, v in sorted(signals.items())
    )


def _generate_analysis(
    ticker: str,
    trade_date: date,
    pct_change: float,
    had_pos: bool,
    signals: dict,
    ensemble: Optional[dict],
) -> str:
    e = ensemble or {}
    prompt = _PROMPT.format(
        date=trade_date,
        regime=e.get("regime", "unknown"),
        ticker=ticker,
        pct_change=pct_change,
        had_position="yes" if had_pos else "no",
        signals_summary=_format_signals(signals),
        final_score=e.get("final_score", 0.0),
        target_weight=e.get("target_weight", 0.0),
        component_scores=e.get("component_scores", {}),
    )
    resp = _client().chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": "You are a quantitative analyst. Be concise and precise."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=350,
        temperature=0.3,
    )
    return resp.choices[0].message.content.strip()


def _insert_missed(
    ticker: str,
    trade_date: date,
    close: float,
    pct_change: float,
    regime: str,
    signals: dict,
    daily_return: float,
    spy_return: Optional[float],
    reflection: str,
) -> int:
    action = "missed_buy" if pct_change > 0 else "missed_exit"
    alpha = (daily_return - spy_return) if spy_return is not None else None
    with conn() as c, c.cursor() as cur:
        cur.execute(
            """
            INSERT INTO trade_memory
              (ticker, trade_date, action, entry_price, signals, debate_summary,
               regime, status, actual_return_5d, alpha_vs_spy_5d,
               reflection, resolved_date, label)
            VALUES (%s,%s,%s,%s,%s,%s,%s,'resolved',%s,%s,%s,%s,'Missed')
            RETURNING id
            """,
            (
                ticker,
                trade_date,
                action,
                close,
                Jsonb(signals),
                f"Biggest mover: {pct_change:+.2f}% — no trade executed",
                regime,
                daily_return,
                alpha,
                reflection,
                trade_date,
            ),
        )
        row_id = cur.fetchone()[0]
        c.commit()
    return row_id


def _already_universe_miss(ticker: str, trade_date: date) -> bool:
    with conn() as c, c.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM trade_memory WHERE ticker=%s AND trade_date=%s AND label='Universe Miss' LIMIT 1",
            (ticker, trade_date),
        )
        return cur.fetchone() is not None


def _get_volume_ratio(ticker: str, trade_date: date) -> tuple[int, int, float]:
    """Returns (today_vol, avg_20d_vol, ratio). Falls back to (0,0,0) on missing data."""
    with conn() as c, c.cursor() as cur:
        cur.execute(
            """
            SELECT date, volume FROM ohlcv_daily
            WHERE ticker = %s AND date <= %s
            ORDER BY date DESC LIMIT 21
            """,
            (ticker, trade_date),
        )
        rows = cur.fetchall()
    if not rows:
        return 0, 0, 0.0
    today_vol = int(rows[0][1])
    prior_vols = [int(r[1]) for r in rows[1:]] if len(rows) > 1 else [1]
    avg_vol = int(sum(prior_vols) / len(prior_vols)) if prior_vols else 1
    ratio = today_vol / avg_vol if avg_vol else 0.0
    return today_vol, avg_vol, ratio


def _generate_universe_miss_analysis(
    ticker: str, trade_date: date, pct_change: float,
    volume_today: int, volume_avg: int, volume_ratio: float,
) -> str:
    import yfinance as yf
    try:
        info = yf.Ticker(ticker).info
        sector = info.get("sector", "Unknown")
    except Exception:
        sector = "Unknown"

    prompt = _UNIVERSE_MISS_PROMPT.format(
        date=trade_date,
        ticker=ticker,
        sector=sector,
        pct_change=pct_change,
        volume_today=volume_today,
        volume_avg=volume_avg,
        volume_ratio=volume_ratio,
    )
    resp = _client().chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": "You are a quantitative analyst. Be concise and precise."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=300,
        temperature=0.3,
    )
    return resp.choices[0].message.content.strip()


def _insert_universe_miss(
    ticker: str, trade_date: date, close: float,
    pct_change: float, daily_return: float, spy_return: Optional[float],
    reflection: str,
) -> int:
    alpha = (daily_return - spy_return) if spy_return is not None else None
    with conn() as c, c.cursor() as cur:
        cur.execute(
            """
            INSERT INTO trade_memory
              (ticker, trade_date, action, entry_price, signals, debate_summary,
               regime, status, actual_return_5d, alpha_vs_spy_5d,
               reflection, resolved_date, label)
            VALUES (%s,%s,'universe_miss',%s,%s,%s,'unknown','resolved',%s,%s,%s,%s,'Universe Miss')
            RETURNING id
            """,
            (
                ticker, trade_date, close,
                Jsonb({}),
                f"Extended watchlist: moved {pct_change:+.2f}% — not in trading universe",
                daily_return, alpha, reflection, trade_date,
            ),
        )
        row_id = cur.fetchone()[0]
        c.commit()
    return row_id


def _scan_extended_watchlist(
    trade_date: date,
    extended_tickers: list[str],
    spy_return: Optional[float],
) -> dict:
    """Scan extended watchlist for big movers outside the active universe."""
    movers = _get_movers(trade_date, extended_tickers)[:TOP_N_EXTENDED]
    analyzed = skipped = 0

    for m in movers:
        ticker, pct = m["ticker"], m["pct_change"]

        if _already_universe_miss(ticker, trade_date):
            skipped += 1
            continue

        volume_today, volume_avg, volume_ratio = _get_volume_ratio(ticker, trade_date)

        try:
            reflection = _generate_universe_miss_analysis(
                ticker, trade_date, pct, volume_today, volume_avg, volume_ratio,
            )
        except Exception:
            log.exception("universe_miss LLM failed for %s", ticker)
            reflection = (
                f"{ticker} moved {pct:+.2f}% outside the trading universe. "
                f"Volume ratio: {volume_ratio:.1f}x. Consider adding to seed universe."
            )

        row_id = _insert_universe_miss(
            ticker, trade_date, m["close"], pct, pct / 100, spy_return, reflection,
        )
        log.info("universe_miss inserted id=%d %s %s %+.2f%%", row_id, ticker, trade_date, pct)
        analyzed += 1

    return {"universe_miss_analyzed": analyzed, "universe_miss_skipped": skipped}


def run_eod_mover_analysis(trade_date: Optional[date] = None) -> dict:
    """Analyze the day's biggest movers that weren't traded.

    Idempotent — skips tickers already analyzed for the given date.
    Returns summary dict for pipeline logging.
    """
    if trade_date is None:
        trade_date = _latest_trade_date()
    if trade_date is None:
        log.warning("run_eod_mover_analysis: no ohlcv data found")
        return {"date": None, "movers_found": 0, "analyzed": 0}

    cfg = universe_cfg()
    tickers = cfg["seed_tickers"]
    extended_tickers = cfg.get("extended_watchlist", [])
    spy_return = _spy_daily_return(trade_date)
    movers = _get_movers(trade_date, tickers)
    log.info(
        "run_eod_mover_analysis: date=%s found %d movers >= %.1f%%",
        trade_date, len(movers), MIN_MOVE_PCT,
    )

    analyzed = skipped_traded = skipped_done = 0

    for m in movers:
        ticker, pct = m["ticker"], m["pct_change"]

        if _was_traded(ticker, trade_date):
            log.info("run_eod_mover_analysis: %s was traded today — skipping", ticker)
            skipped_traded += 1
            continue

        if _already_analyzed(ticker, trade_date):
            log.info("run_eod_mover_analysis: %s already analyzed for %s — skipping", ticker, trade_date)
            skipped_done += 1
            continue

        signals = _get_signals(ticker, trade_date)
        ensemble = _get_ensemble(ticker, trade_date)
        had_pos = _has_position(ticker)
        regime = ensemble["regime"] if ensemble else "unknown"

        try:
            reflection = _generate_analysis(ticker, trade_date, pct, had_pos, signals, ensemble)
        except Exception:
            log.exception("run_eod_mover_analysis: LLM call failed for %s", ticker)
            reflection = f"Analysis unavailable. Move: {pct:+.2f}%."

        row_id = _insert_missed(
            ticker, trade_date, m["close"], pct,
            regime, signals, pct / 100, spy_return, reflection,
        )
        log.info(
            "run_eod_mover_analysis: inserted id=%d %s %s %+.2f%%",
            row_id, ticker, trade_date, pct,
        )
        analyzed += 1

    # Also scan extended watchlist for Universe Miss entries
    ext_result = {}
    if extended_tickers:
        # Only scan extended tickers we have OHLCV for (those already backfilled)
        with conn() as c, c.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT ticker FROM ohlcv_daily WHERE ticker = ANY(%s) AND date = %s",
                (extended_tickers, trade_date),
            )
            tracked_extended = [r[0] for r in cur.fetchall()]
        if tracked_extended:
            ext_result = _scan_extended_watchlist(trade_date, tracked_extended, spy_return)

    result = {
        "date": str(trade_date),
        "movers_found": len(movers),
        "analyzed": analyzed,
        "skipped_traded": skipped_traded,
        "skipped_already_done": skipped_done,
        **ext_result,
    }
    log_activity("eod_mover_analysis", "run", "ok", **result)
    return result
