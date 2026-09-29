"""Deferred LLM reflection over resolved trades — computes 5-day returns and asks DeepSeek
to generate a post-mortem for each pending trade_memory row."""
from __future__ import annotations

import os

from openai import OpenAI

from src.core.db import conn
from src.core.logging import get_logger
from src.strategy.memory.trade_memory import get_pending_reflections, update_reflection

log = get_logger("reflector")

_REFLECTION_PROMPT = """\
You are a quantitative analyst performing a post-mortem on a recent trade decision.

Trade details:
- Ticker: {ticker}
- Date: {trade_date}
- Action: {action}
- Entry price: {entry_price}
- Regime at entry: {regime}
- Signals used: {signals}
- Debate summary: {debate_summary}
- Actual 5-day return: {actual_return:.4f} ({actual_return_pct:.2f}%)
- Alpha vs SPY over 5 days: {alpha:.4f} ({alpha_pct:.2f}%)

Write a concise (3-5 sentence) post-mortem reflection covering:
1. Whether the entry thesis was correct given the outcome.
2. What signals were most/least informative in hindsight.
3. One actionable lesson for future similar setups.

Be specific and quantitative. Avoid generic statements.
"""


def _get_openai_client() -> OpenAI:
    return OpenAI(
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url="https://api.deepseek.com",
    )


def _fetch_5d_return(ticker: str, trade_date: str) -> float | None:
    """Compute the 5-trading-day return from trade_date using ohlcv_daily."""
    try:
        with conn() as c, c.cursor() as cur:
            # Get the entry close on trade_date
            cur.execute(
                """
                SELECT close FROM ohlcv_daily
                WHERE ticker = %s AND date = %s
                """,
                (ticker, trade_date),
            )
            entry_row = cur.fetchone()
            if not entry_row or entry_row[0] is None:
                return None

            entry_close = float(entry_row[0])

            # Get the 5th trading day after trade_date
            cur.execute(
                """
                SELECT close FROM ohlcv_daily
                WHERE ticker = %s AND date > %s
                ORDER BY date ASC
                LIMIT 1 OFFSET 4
                """,
                (ticker, trade_date),
            )
            exit_row = cur.fetchone()
            if not exit_row or exit_row[0] is None:
                return None

            exit_close = float(exit_row[0])
            if entry_close <= 0:
                return None

            return (exit_close - entry_close) / entry_close

    except Exception:
        log.exception("_fetch_5d_return failed for %s %s", ticker, trade_date)
        return None


def _fetch_spy_5d_return(trade_date: str) -> float | None:
    """Compute SPY 5-day return for the same window."""
    return _fetch_5d_return("SPY", trade_date)


def _generate_reflection(row: dict, actual_return: float, alpha: float) -> str:
    """Call DeepSeek to generate a post-mortem reflection."""
    client = _get_openai_client()

    prompt = _REFLECTION_PROMPT.format(
        ticker=row["ticker"],
        trade_date=str(row["trade_date"]),
        action=row["action"],
        entry_price=float(row["entry_price"] or 0),
        regime=row.get("regime", "unknown"),
        signals=row.get("signals", {}),
        debate_summary=row.get("debate_summary", ""),
        actual_return=actual_return,
        actual_return_pct=actual_return * 100,
        alpha=alpha,
        alpha_pct=alpha * 100,
    )

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {
                "role": "system",
                "content": "You are a quantitative analyst. Be concise and precise.",
            },
            {"role": "user", "content": prompt},
        ],
        max_tokens=300,
        temperature=0.3,
    )
    return response.choices[0].message.content.strip()


def run_reflections() -> int:
    """Process all pending trade_memory rows that are >5 days old.

    For each row:
    1. Fetch the actual 5-day return from ohlcv_daily.
    2. Compute alpha vs SPY.
    3. Call DeepSeek to generate a reflection.
    4. Mark the row as resolved via update_reflection().

    Returns the number of rows processed.
    """
    pending = get_pending_reflections(days_old=5)
    log.info("run_reflections: found %d pending rows", len(pending))

    processed = 0
    for row in pending:
        trade_id = row["id"]
        ticker = row["ticker"]
        trade_date = str(row["trade_date"])

        actual_return = _fetch_5d_return(ticker, trade_date)
        if actual_return is None:
            log.warning(
                "run_reflections: no 5d return data for %s %s, skipping",
                ticker,
                trade_date,
            )
            continue

        spy_return = _fetch_spy_5d_return(trade_date)
        alpha = (actual_return - spy_return) if spy_return is not None else 0.0

        try:
            reflection_text = _generate_reflection(row, actual_return, alpha)
        except Exception:
            log.exception(
                "run_reflections: LLM reflection failed for id=%d, using fallback", trade_id
            )
            reflection_text = (
                f"Automated reflection unavailable. "
                f"5d return: {actual_return:.4f}, alpha: {alpha:.4f}."
            )

        update_reflection(
            id=trade_id,
            actual_return=actual_return,
            alpha=alpha,
            reflection=reflection_text,
        )
        processed += 1
        log.info(
            "run_reflections: resolved id=%d ticker=%s return=%.4f alpha=%.4f",
            trade_id,
            ticker,
            actual_return,
            alpha,
        )

    return processed
