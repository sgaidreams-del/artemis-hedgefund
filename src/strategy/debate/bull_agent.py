from __future__ import annotations

import os
from openai import OpenAI
from src.strategy.debate.checklist_scorer import BullChecklist
from src.strategy.debate.prompts import BULL_AGENT_SYSTEM, BULL_AGENT_USER
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
    checklist: BullChecklist,
    signals_summary: str,
    recent_news: list[str],
) -> str:
    """
    Make the bull case for ticker. Returns argument text.
    Returns empty string on failure.
    """
    news_text = "\n".join(f"- {h}" for h in recent_news[:3]) if recent_news else "- None"
    user_msg = BULL_AGENT_USER.format(
        ticker=ticker,
        momentum_score=checklist.momentum_score,
        quality_score=checklist.quality_score,
        value_score=checklist.value_score,
        contrarian_score=checklist.contrarian_score,
        total=checklist.total,
        signals_summary=signals_summary,
        news=news_text,
    )
    try:
        client = _get_client()
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": BULL_AGENT_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.3,
            max_tokens=150,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.warning(f"Bull agent failed for {ticker}: {e}")
        return ""
