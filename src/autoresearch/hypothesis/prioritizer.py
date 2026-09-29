"""Hypothesis prioritizer — ranks by expected_alpha × novelty_score."""
from __future__ import annotations

from src.core.logging import get_logger

log = get_logger(__name__)


def _title_words(title: str) -> set[str]:
    """Return lowercase words from a title, stripped of punctuation."""
    import re
    return set(re.sub(r"[^a-z0-9 ]", "", title.lower()).split())


def _novelty_score(hypothesis: dict, journal_entries: list[dict]) -> float:
    """Compute 1 - max_similarity_to_past_experiments.

    Similarity = Jaccard overlap of title words between hypothesis and each
    past journal entry description / hypothesis_id.
    """
    h_words = _title_words(hypothesis.get("title", ""))
    if not h_words:
        return 1.0

    max_sim = 0.0
    for entry in journal_entries:
        past_title = entry.get("description", entry.get("hypothesis_id", ""))
        p_words = _title_words(str(past_title))
        if not p_words:
            continue
        intersection = len(h_words & p_words)
        union = len(h_words | p_words)
        sim = intersection / union if union else 0.0
        if sim > max_sim:
            max_sim = sim

    return 1.0 - max_sim


def prioritize(hypotheses: list[dict], journal_entries: list[dict]) -> list[dict]:
    """Rank hypotheses by expected_alpha * novelty_score (descending).

    Modifies each hypothesis dict in-place to add a ``score`` key, then
    returns a new list sorted highest score first.
    """
    log.info("prioritize", n_hypotheses=len(hypotheses), n_journal=len(journal_entries))

    for h in hypotheses:
        alpha = float(h.get("expected_alpha", 0.0))
        novelty = _novelty_score(h, journal_entries)
        h["novelty_score"] = round(novelty, 4)
        h["score"] = round(alpha * novelty, 6)

    ranked = sorted(hypotheses, key=lambda h: h["score"], reverse=True)
    log.info("prioritize_done", ranked_ids=[h.get("id") for h in ranked])
    return ranked
