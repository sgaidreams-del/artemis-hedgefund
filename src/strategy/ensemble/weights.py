"""Ensemble signal weights — loaded from DB, falling back to hard-coded defaults."""
from __future__ import annotations

from datetime import datetime, timezone

from src.core.db import conn
from src.core.logging import get_logger

log = get_logger("ensemble.weights")

DEFAULT_WEIGHTS: dict[str, float] = {
    "sentiment_1d": 0.15,
    "sentiment_7d": 0.10,
    "technical_composite": 0.20,
    "llm_sentiment": 0.15,
    "regime_overlay": 0.10,
    "insider_signal": 0.10,
    "short_interest_signal": 0.10,
    "options_flow_signal": 0.10,
    # Not in the original SPEC weighting — added when qlib_alpha (Unit 7) was
    # found to have no entry in any ensemble weight scheme, so its output was
    # silently dropped from every score. _combine_with_weights renormalizes by
    # whatever weight is actually present, so this doesn't need to sum to 1.0.
    "qlib_alpha": 0.15,
    # Volume anomaly amplifier: non-directional (always ≥ 0) — raises ensemble
    # confidence when unusual volume confirms other bullish signals. Weight is
    # intentionally low; it acts as a multiplier on conviction, not a direction call.
    "volume_anomaly_signal": 0.05,
}


def load_weights() -> dict[str, float]:
    """Read ensemble weights from feature_metadata WHERE category='ensemble_weight'.

    Falls back to DEFAULT_WEIGHTS if no rows are found.
    """
    try:
        with conn() as c, c.cursor() as cur:
            cur.execute(
                """
                SELECT feature_name, computation_version
                FROM feature_metadata
                WHERE category = 'ensemble_weight'
                """,
            )
            rows = cur.fetchall()

        if not rows:
            log.info("no ensemble weights in DB — using defaults")
            return dict(DEFAULT_WEIGHTS)

        weights: dict[str, float] = {}
        for feature_name, computation_version in rows:
            try:
                weights[feature_name] = float(computation_version)
            except (TypeError, ValueError):
                log.warning("bad weight value for %s, skipping", feature_name)

        if not weights:
            return dict(DEFAULT_WEIGHTS)

        # Fill any missing keys with defaults
        for key, default_val in DEFAULT_WEIGHTS.items():
            if key not in weights:
                weights[key] = default_val

        return weights

    except Exception:
        log.exception("load_weights failed, using defaults")
        return dict(DEFAULT_WEIGHTS)


def save_weights(weights: dict[str, float]) -> None:
    """Upsert each weight into feature_metadata (stored in computation_version column)."""
    now = datetime.now(timezone.utc)
    try:
        with conn() as c, c.cursor() as cur:
            for feature_name, value in weights.items():
                cur.execute(
                    """
                    INSERT INTO feature_metadata (feature_name, category, computation_version, last_updated)
                    VALUES (%s, 'ensemble_weight', %s, %s)
                    ON CONFLICT (feature_name) DO UPDATE
                        SET category = EXCLUDED.category,
                            computation_version = EXCLUDED.computation_version,
                            last_updated = EXCLUDED.last_updated
                    """,
                    (feature_name, str(value), now),
                )
            c.commit()
        log.info("saved %d ensemble weights", len(weights))
    except Exception:
        log.exception("save_weights failed")
        raise
