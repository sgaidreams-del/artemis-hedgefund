"""FinBERT sentiment scoring for news headlines."""
from __future__ import annotations

from transformers import pipeline

_pipe = None


def get_pipeline():
    """Lazy-load the ProsusAI/finbert sentiment pipeline (CPU only)."""
    global _pipe
    if _pipe is None:
        _pipe = pipeline(
            "text-classification",
            model="ProsusAI/finbert",
            cache_dir="models/finbert",
            device=-1,
        )
    return _pipe


_LABEL_MAP: dict[str, float] = {
    "positive": 1.0,
    "negative": -1.0,
    "neutral": 0.0,
}


def score_headlines(texts: list[str]) -> list[float]:
    """Score a list of headlines with FinBERT.

    Returns a list of floats in [-1, +1], where each value is
    label_direction * confidence_score.  Empty input returns [].
    Errors return [0.0] * len(texts).
    """
    if not texts:
        return []

    try:
        pipe = get_pipeline()
    except Exception:
        return [0.0] * len(texts)

    results: list[float] = []
    batch_size = 16
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        try:
            outputs = pipe(batch)
            for out in outputs:
                label = out["label"].lower()
                direction = _LABEL_MAP.get(label, 0.0)
                results.append(direction * out["score"])
        except Exception:
            results.extend([0.0] * len(batch))
    return results
