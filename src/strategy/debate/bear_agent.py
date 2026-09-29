from __future__ import annotations

import os
from openai import OpenAI
from src.strategy.debate.checklist_scorer import BearChecklist
from src.strategy.debate.prompts import BEAR_AGENT_SYSTEM, BEAR_AGENT_USER
from src.core.logging import get_logger

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


def make_case(
    ticker: str,
    checklist: BearChecklist,
    signals_summary: str,
    recent_news: list[str],
) -> str:
    """Make the bear case for ticker. Returns argument text."""
    news_text = "\n".join(f"- {h}" for h in recent_news[:3]) if recent_news else "- None"
    user_msg = BEAR_AGENT_USER.format(
        ticker=ticker,
        momentum_score=checklist.momentum_score,
        overvaluation_score=checklist.overvaluation_score,
        risk_score=checklist.risk_score,
        sentiment_score=checklist.sentiment_score,
        total=checklist.total,
        signals_summary=signals_summary,
        news=news_text,
    )
    try:
        client = _get_client()
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": BEAR_AGENT_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.3,
            max_tokens=150,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.warning(f"Bear agent failed for {ticker}: {e}")
        return ""
