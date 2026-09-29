"""DeepSeek LLM-based per-ticker sentiment analyzer. SPEC §LLM / Unit 4."""
from __future__ import annotations

import json
import os
import time
from datetime import date

from openai import OpenAI

from src.core.config import settings as cfg
from src.core.db import conn
from src.core.logging import get_logger
from dashboard_api.routers.kill_switch import is_paused
from .prompts import TICKER_ANALYSIS_SYSTEM, TICKER_ANALYSIS_USER

logger = get_logger(__name__)


def _get_ticker_context(ticker: str) -> dict:
    """Read most recent fundamentals row from DB for ticker.

    Returns dict with pe_ratio, market_cap_b, dividend_yield, sector.
    Falls back to None values if no row found.
    """
    with conn() as c, c.cursor() as cur:
        cur.execute(
            """
            SELECT pe_ratio, market_cap, dividend_yield, sector
            FROM fundamentals
            WHERE ticker = %s
            ORDER BY asof_date DESC
            LIMIT 1
            """,
            (ticker,),
        )
        row = cur.fetchone()

    if row is None:
        logger.warning("no_fundamentals_found", ticker=ticker)
        return {
            "pe_ratio": None,
            "market_cap_b": None,
            "dividend_yield": None,
            "sector": None,
        }

    pe_ratio, market_cap, dividend_yield, sector = row
    market_cap_b = round(float(market_cap) / 1e9, 2) if market_cap is not None else None
    return {
        "pe_ratio": pe_ratio,
        "market_cap_b": market_cap_b,
        "dividend_yield": dividend_yield,
        "sector": sector,
    }


def analyze_ticker(
    ticker: str,
    fundamentals: dict,
    recent_headlines: list[str],
    technical_score: float,
) -> dict | None:
    """Build prompt, call deepseek-chat, parse JSON response.

    Expected JSON: {bull_points, bear_points, sentiment_score, confidence}
    Returns None on any error.
    """
    try:
        headlines_text = "\n".join(
            f"  - {h}" for h in recent_headlines
        ) if recent_headlines else "  (no recent headlines)"

        user_prompt = TICKER_ANALYSIS_USER.format(
            ticker=ticker,
            pe_ratio=fundamentals.get("pe_ratio", "N/A"),
            market_cap_b=fundamentals.get("market_cap_b", "N/A"),
            dividend_yield=fundamentals.get("dividend_yield", "N/A"),
            sector=fundamentals.get("sector", "N/A"),
            technical_score=technical_score,
            headlines=headlines_text,
        )

        client = OpenAI(
            api_key=os.environ["DEEPSEEK_API_KEY"],
            base_url="https://api.deepseek.com",
        )

        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": TICKER_ANALYSIS_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        )

        raw = response.choices[0].message.content.strip()
        result = json.loads(raw)

        required_keys = {"bull_points", "bear_points", "sentiment_score", "confidence"}
        if not required_keys.issubset(result.keys()):
            missing = required_keys - result.keys()
            logger.error("llm_response_missing_keys", ticker=ticker, missing=list(missing))
            return None

        logger.info(
            "llm_analysis_ok",
            ticker=ticker,
            sentiment_score=result["sentiment_score"],
            confidence=result["confidence"],
        )
        return result

    except json.JSONDecodeError as exc:
        logger.error("llm_json_parse_error", ticker=ticker, err=str(exc))
        return None
    except Exception as exc:
        logger.error("llm_analyze_error", ticker=ticker, err=str(exc))
        return None


def run_llm_pipeline(
    tickers: list[str],
    max_per_day: int | None = None,
) -> int:
    """Run LLM analysis for each ticker, upsert signal to DB.

    max_per_day defaults to cfg()["llm"]["max_holdings_analyzed_per_day"].
    Rate limit: sleep 1s between calls.
    Skip if is_paused().
    Returns count of tickers processed.
    """
    if max_per_day is None:
        max_per_day = cfg()["llm"]["max_holdings_analyzed_per_day"]

    slice_ = tickers[:max_per_day]
    today = date.today()
    processed = 0

    for i, ticker in enumerate(slice_):
        if is_paused():
            logger.info("llm_pipeline_paused", ticker=ticker)
            break

        try:
            fundamentals = _get_ticker_context(ticker)
            result = analyze_ticker(
                ticker=ticker,
                fundamentals=fundamentals,
                recent_headlines=[],
                technical_score=0.0,
            )

            if result is None:
                logger.warning("llm_pipeline_skip_null_result", ticker=ticker)
            else:
                sentiment_score = result["sentiment_score"]
                confidence = result["confidence"]

                with conn() as c, c.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO signals (ticker, date, signal_name, value, confidence)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (ticker, date, signal_name)
                        DO UPDATE SET
                            value      = EXCLUDED.value,
                            confidence = EXCLUDED.confidence
                        """,
                        (ticker, today, "llm_sentiment", sentiment_score, confidence),
                    )
                    c.commit()

                logger.info("llm_signal_upserted", ticker=ticker, date=str(today))
                processed += 1

        except Exception as exc:
            logger.error("llm_pipeline_error", ticker=ticker, err=str(exc))

        if i < len(slice_) - 1:
            time.sleep(1)

    return processed
