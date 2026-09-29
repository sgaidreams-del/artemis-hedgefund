"""Hypothesis generator — calls DeepSeek to produce research hypotheses."""
from __future__ import annotations

import json
import os

from openai import OpenAI

from src.core.logging import get_logger
from src.autoresearch.journal.manager import get_recent
from src.autoresearch.hypothesis.templates import (
    HYPOTHESIS_GENERATION_SYSTEM,
    HYPOTHESIS_GENERATION_USER,
)

log = get_logger(__name__)


def _build_journal_summary(entries: list[dict]) -> str:
    if not entries:
        return "No prior journal entries found."
    lines = []
    for e in entries:
        title = e.get("description", e.get("hypothesis_id", "unknown"))
        result = e.get("result", "pending")
        perf = e.get("performance") or {}
        sharpe = perf.get("sharpe", "n/a") if isinstance(perf, dict) else "n/a"
        lines.append(f"- [{e.get('category', '?')}] {title} | result={result} | sharpe={sharpe}")
    return "\n".join(lines)


def _build_performance_summary(entries: list[dict]) -> str:
    deployed = [e for e in entries if e.get("result") == "DEPLOY"]
    if not deployed:
        return "No deployed strategies found yet."
    sharpes = []
    for e in deployed:
        perf = e.get("performance") or {}
        if isinstance(perf, dict) and "sharpe" in perf:
            try:
                sharpes.append(float(perf["sharpe"]))
            except (TypeError, ValueError):
                pass
    if sharpes:
        avg = sum(sharpes) / len(sharpes)
        return f"Deployed strategies: {len(deployed)}. Average Sharpe: {avg:.2f}."
    return f"Deployed strategies: {len(deployed)}. No Sharpe data available."


def generate_hypotheses(n: int = 5) -> list[dict]:
    """Read 20 recent research_journal entries. Call deepseek-chat.

    Returns list of {id, title, signal_type, rationale, expected_alpha, priority}.
    """
    log.info("generate_hypotheses", n=n)

    entries = get_recent(n=20)
    journal_summary = _build_journal_summary(entries)
    performance_summary = _build_performance_summary(entries)

    client = OpenAI(
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url="https://api.deepseek.com",
    )

    user_prompt = HYPOTHESIS_GENERATION_USER.format(
        recent_journal_summary=journal_summary,
        performance_summary=performance_summary,
        n=n,
    )

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": HYPOTHESIS_GENERATION_SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
    )

    raw = response.choices[0].message.content.strip()

    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        raw = raw.rsplit("```", 1)[0].strip()

    hypotheses: list[dict] = json.loads(raw)

    required_keys = {"id", "title", "signal_type", "rationale", "expected_alpha", "priority"}
    validated = []
    for h in hypotheses:
        missing = required_keys - set(h.keys())
        if missing:
            log.warning("hypothesis_missing_keys", missing=list(missing), hypothesis=h)
            continue
        validated.append(h)

    log.info("generate_hypotheses_done", count=len(validated))
    return validated
