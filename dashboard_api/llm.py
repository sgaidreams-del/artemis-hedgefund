"""DeepSeek client — OpenAI-compatible API. Used for event plan-of-action narratives."""
from __future__ import annotations

from functools import lru_cache

from openai import OpenAI

from src.core.config import env


def configured() -> bool:
    return bool(env("DEEPSEEK_API_KEY"))


@lru_cache(maxsize=1)
def _client() -> OpenAI | None:
    if not configured():
        return None
    return OpenAI(api_key=env("DEEPSEEK_API_KEY"), base_url=env("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))


def narrate(system_prompt: str, user_prompt: str, model: str = "deepseek-chat", max_tokens: int = 400) -> str | None:
    """Returns None if DeepSeek isn't configured or the call fails — callers must handle gracefully."""
    client = _client()
    if client is None:
        return None
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=max_tokens,
            temperature=0.3,
        )
        return resp.choices[0].message.content
    except Exception:
        return None
