"""Weekly review — aggregates 7-day performance and journal activity, calls DeepSeek-reasoner."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

from openai import OpenAI

from src.core.db import conn
from src.core.logging import get_logger

log = get_logger(__name__)

_SYSTEM_PROMPT = """You are a senior quantitative portfolio manager conducting a weekly research review.
Analyse the provided journal entries and performance data and produce a structured markdown report.

The report must include:
1. **Executive Summary** (3-4 sentences)
2. **This Week's Experiments** (table or bullet list)
3. **Top Performers** and **Underperformers**
4. **Key Learnings**
5. **Next Week's Research Priorities** (3-5 items)
6. **Risk Flags** (if any)

Be concise, data-driven, and actionable."""


def _get_week_experiments() -> list[dict]:
    since = datetime.now(timezone.utc) - timedelta(days=7)
    sql = """
        SELECT experiment_id, hypothesis_id, category, description,
               result, performance, learnings, created_at
        FROM research_journal
        WHERE created_at >= %s
        ORDER BY created_at DESC
    """
    try:
        with conn() as c, c.cursor() as cur:
            cur.execute(sql, (since,))
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]
    except Exception as exc:
        log.warning("weekly_review_db_error", error=str(exc))
        return []

    entries = []
    for row in rows:
        entry = dict(zip(cols, row))
        for field in ("performance",):
            val = entry.get(field)
            if isinstance(val, str):
                try:
                    entry[field] = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    pass
        entries.append(entry)
    return entries


def _summarize_experiments(entries: list[dict]) -> str:
    if not entries:
        return "No experiments this week."
    lines = [f"Total experiments: {len(entries)}\n"]
    for e in entries:
        perf = e.get("performance") or {}
        sharpe = perf.get("sharpe", "n/a") if isinstance(perf, dict) else "n/a"
        lines.append(
            f"- [{e.get('category', '?')}] {e.get('description', e.get('hypothesis_id', '?'))} "
            f"| result={e.get('result', 'pending')} | sharpe={sharpe}"
        )
    return "\n".join(lines)


def run_weekly_review() -> str:
    """Read 7-day performance + journal. Call deepseek-reasoner.

    Returns a markdown report string.
    """
    log.info("run_weekly_review")

    entries = _get_week_experiments()
    summary = _summarize_experiments(entries)

    client = OpenAI(
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url="https://api.deepseek.com",
    )

    week_label = datetime.now(timezone.utc).strftime("%Y-W%U")
    user_prompt = (
        f"Week: {week_label}\n\n"
        f"Research journal — last 7 days:\n{summary}\n\n"
        f"Please produce the weekly review report."
    )

    response = client.chat.completions.create(
        model="deepseek-reasoner",
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )

    report = response.choices[0].message.content.strip()
    log.info("run_weekly_review_done", chars=len(report))
    return report
