"""Experiment analyzer — calls DeepSeek to produce a verdict on experiment results."""
from __future__ import annotations

import json
import os

from openai import OpenAI

from src.core.logging import get_logger

log = get_logger(__name__)

_SYSTEM_PROMPT = """You are a quantitative research analyst reviewing backtested trading strategy results.
Given a hypothesis and its scorecard metrics, produce a structured verdict.

Output a JSON object with exactly these fields:
- verdict: one of "DEPLOY", "ITERATE", or "ABANDON"
- commentary: string (3-5 sentences explaining the verdict)
- next_steps: list of strings (2-4 concrete action items)

Guidance:
- DEPLOY: Sharpe > 1.0, max drawdown > -0.20, total_return > 0.05
- ITERATE: Sharpe 0.3-1.0 or promising signal needing refinement
- ABANDON: Sharpe < 0.3, max drawdown < -0.40, or fundamental flaw

Output ONLY the JSON object."""


def analyze_result(hypothesis: dict, scorecard_result: dict) -> dict:
    """Call deepseek-chat to analyse scorecard results.

    Returns {verdict: 'DEPLOY'|'ITERATE'|'ABANDON', commentary, next_steps}.
    """
    log.info("analyze_result", hypothesis_id=hypothesis.get("id"))

    client = OpenAI(
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url="https://api.deepseek.com",
    )

    user_prompt = (
        f"Hypothesis:\n{json.dumps(hypothesis, indent=2)}\n\n"
        f"Scorecard results:\n{json.dumps(scorecard_result, indent=2)}"
    )

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
    )

    raw = response.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        raw = raw.rsplit("```", 1)[0].strip()

    analysis: dict = json.loads(raw)

    verdict = analysis.get("verdict", "ITERATE")
    if verdict not in {"DEPLOY", "ITERATE", "ABANDON"}:
        log.warning("unexpected_verdict", verdict=verdict)
        analysis["verdict"] = "ITERATE"

    log.info("analyze_result_done", verdict=analysis.get("verdict"))
    return analysis
