from __future__ import annotations

import os
import json
from openai import OpenAI
from src.strategy.debate.checklist_scorer import (
    BullChecklist, BearChecklist, score_bull_checklist, score_bear_checklist
)
from src.strategy.debate.prompts import JUDGE_SYSTEM, JUDGE_USER
from src.strategy.debate import bull_agent, bear_agent
from src.core.logging import get_logger
from dashboard_api.routers.kill_switch import is_paused

logger = get_logger(__name__)

_client = None

def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
            base_url="https://api.deepseek.com",
        )
    return _client


def adjudicate(
    ticker: str,
    bull_case: str,
    bear_case: str,
    bull_checklist: BullChecklist,
    bear_checklist: BearChecklist,
) -> dict:
    """
    Judge the debate. Calls deepseek-reasoner.
    Returns {verdict, confidence, reasoning, winning_side}.
    On failure, returns {verdict:"hold", confidence:0.0, reasoning:"judge_error"}.
    """
    user_msg = JUDGE_USER.format(
        ticker=ticker,
        bull_total=bull_checklist.total,
        bear_total=bear_checklist.total,
        bull_case=bull_case or "(no argument)",
        bear_case=bear_case or "(no argument)",
    )
    try:
        client = _get_client()
        resp = client.chat.completions.create(
            model="deepseek-reasoner",
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.0,
            max_tokens=400,
        )
        raw = resp.choices[0].message.content.strip()
        if raw.startswith("```"):
            # Strip opening fence line (```json or ```) and any trailing fence
            # Handles both "```json\n{...}\n```" and "```json\n{...}```"
            lines = raw.split("\n")
            inner_lines = lines[1:]  # drop opening fence line
            # Drop standalone closing fence line if present
            if inner_lines and inner_lines[-1].strip() == "```":
                inner_lines = inner_lines[:-1]
            raw = "\n".join(inner_lines)
            # Strip trailing ``` suffix if the JSON line itself ends with the fence
            if raw.endswith("```"):
                raw = raw[: -3].rstrip()
        result = json.loads(raw)
        return {
            "verdict": result.get("verdict", "hold"),
            "confidence": float(result.get("confidence", 0.5)),
            "reasoning": result.get("reasoning", ""),
            "winning_side": result.get("winning_side", "tie"),
        }
    except Exception as e:
        logger.warning(f"Judge failed for {ticker}: {e}")
        return {"verdict": "hold", "confidence": 0.0, "reasoning": f"error: {e}", "winning_side": "tie"}


def run_debate(
    ticker: str,
    signals: dict,
    fundamentals: dict,
    news_headlines: list[str],
) -> dict | None:
    """
    Full debate pipeline for a ticker.
    Returns verdict dict or None if skipped.

    Skips if:
    - Kill switch is paused
    - Signal composite is strongly one-sided (|value| > 0.8) — no debate needed
    """
    if is_paused():
        return None

    # Skip if signal is strongly one-sided — save LLM cost
    available_weights = {
        "technical_composite": 0.35,
        "llm_sentiment": 0.35,
        "sentiment_1d": 0.30,
    }
    quick_composite = 0.0
    w_total = 0.0
    for sig, w in available_weights.items():
        if sig in signals:
            quick_composite += signals[sig] * w
            w_total += w
    if w_total > 0:
        quick_composite /= w_total
        if abs(quick_composite) > 0.8:
            logger.debug(f"{ticker}: skipping debate (composite={quick_composite:.2f} too one-sided)")
            return None

    # Score checklists
    bull_cl = score_bull_checklist(ticker, signals, fundamentals)
    bear_cl = score_bear_checklist(ticker, signals, fundamentals)

    # Format signals summary for agents (guard against non-numeric signal values)
    signals_summary = "\n".join(
        f"  {k}: {v:+.2f}" if isinstance(v, (int, float)) else f"  {k}: {v}"
        for k, v in sorted(signals.items())
    )

    # Run agents
    bull_case = bull_agent.make_case(ticker, bull_cl, signals_summary, news_headlines)
    bear_case = bear_agent.make_case(ticker, bear_cl, signals_summary, news_headlines)

    # Judge
    verdict = adjudicate(ticker, bull_case, bear_case, bull_cl, bear_cl)
    verdict["bull_score"] = bull_cl.total
    verdict["bear_score"] = bear_cl.total
    verdict["ticker"] = ticker

    logger.info(f"Debate verdict for {ticker}: {verdict['verdict']} (confidence={verdict['confidence']:.2f})")
    return verdict
