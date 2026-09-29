"""HMM Regime Detector — GaussianHMM 5-state regime detection."""
from __future__ import annotations

import json
import pickle
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM

from src.core.db import conn
from src.core.logging import get_logger, log_activity
from src.signals.regime.features import build_regime_features

logger = get_logger(__name__)

MODEL_PATH = Path(__file__).resolve().parents[3] / "models" / "regime_hmm" / "model.pkl"

# Maximum model age before retraining (30 days in seconds)
_MAX_MODEL_AGE_SECS = 30 * 24 * 3600


def train_hmm(features_df: pd.DataFrame, n_components: int = 5) -> GaussianHMM:
    """Fit GaussianHMM on features_df. Save to MODEL_PATH. Return model."""
    X = features_df.values.astype(float)

    model = GaussianHMM(
        n_components=n_components,
        covariance_type="full",
        n_iter=200,
        random_state=42,
    )
    model.fit(X)

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with MODEL_PATH.open("wb") as f:
        pickle.dump(model, f)

    log_activity(
        component="regime.detector",
        action="train_hmm",
        n_components=n_components,
        rows=len(features_df),
    )
    logger.info("hmm_trained", n_components=n_components, rows=len(features_df))
    return model


def load_model() -> GaussianHMM | None:
    """Load from MODEL_PATH if exists and mtime < 30 days, else return None."""
    if not MODEL_PATH.exists():
        return None

    mtime = MODEL_PATH.stat().st_mtime
    age_secs = datetime.now(timezone.utc).timestamp() - mtime
    if age_secs > _MAX_MODEL_AGE_SECS:
        logger.info("hmm_model_stale", age_days=age_secs / 86400)
        return None

    with MODEL_PATH.open("rb") as f:
        model = pickle.load(f)

    logger.info("hmm_model_loaded")
    return model


def label_regime(state_id: int, means: np.ndarray) -> str:
    """Map HMM state to human label based on feature means.

    Logic: sort states by mean log_return (col 0).
    Top half = bull, bottom half = bear, middle = sideways.
    Within bull/bear, split by vol_20d (col 1): low-vol vs high-vol.
    Labels: 'Bull/Low-Vol', 'Bull/High-Vol', 'Bear/Low-Vol', 'Bear/High-Vol', 'Sideways'
    Use np.argmin/np.argmax to break ties — avoid label collisions when two states have equal vol.
    """
    n = len(means)
    # Sort states by mean log_return (col 0) ascending
    returns = means[:, 0]
    sorted_indices = np.argsort(returns)  # ascending: worst to best

    # Find where state_id sits in the sorted order
    rank = int(np.where(sorted_indices == state_id)[0][0])

    if n == 5:
        # ranks 0,1 = bear; rank 2 = sideways; ranks 3,4 = bull
        if rank == 2:
            return "Sideways"
        elif rank <= 1:
            # Bear — split by vol_20d within the bear group
            bear_indices = sorted_indices[:2]
            vol_vals = means[bear_indices, 1]
            low_vol_pos = int(np.argmin(vol_vals))
            high_vol_pos = int(np.argmax(vol_vals))
            # Find our position within bear group
            our_pos = int(np.where(bear_indices == state_id)[0][0])
            if our_pos == low_vol_pos:
                return "Bear/Low-Vol"
            else:
                return "Bear/High-Vol"
        else:
            # Bull (ranks 3,4) — split by vol_20d within the bull group
            bull_indices = sorted_indices[3:]
            vol_vals = means[bull_indices, 1]
            low_vol_pos = int(np.argmin(vol_vals))
            high_vol_pos = int(np.argmax(vol_vals))
            our_pos = int(np.where(bull_indices == state_id)[0][0])
            if our_pos == low_vol_pos:
                return "Bull/Low-Vol"
            else:
                return "Bull/High-Vol"
    else:
        # Generic fallback for n != 5
        half = n // 2
        if rank > n - 1 - half:
            return "Bull/High-Vol" if rank == n - 1 else "Bull/Low-Vol"
        elif rank < half:
            return "Bear/High-Vol" if rank == 0 else "Bear/Low-Vol"
        else:
            return "Sideways"


def predict_current_regime(model: GaussianHMM, features_df: pd.DataFrame) -> dict:
    """Returns {regime_id, label, confidence, transition_probs}."""
    X = features_df.values.astype(float)

    states = model.predict(X)
    posteriors = model.predict_proba(X)

    current_state = int(states[-1])
    current_posteriors = posteriors[-1]
    confidence = float(current_posteriors[current_state])

    label = label_regime(current_state, model.means_)

    transition_probs = model.transmat_[current_state].tolist()

    result = {
        "regime_id": current_state,
        "label": label,
        "confidence": confidence,
        "transition_probs": transition_probs,
    }
    logger.info("regime_predicted", **result)
    return result


def run_regime_pipeline() -> dict:
    """Load or train model. Predict today's regime. Upsert to regime_history table.
    Returns the regime dict.
    """
    features_df = build_regime_features()

    model = load_model()
    if model is None:
        logger.info("hmm_training_new_model")
        model = train_hmm(features_df)

    regime = predict_current_regime(model, features_df)

    today = date.today().isoformat()
    transition_probs_json = json.dumps(regime["transition_probs"])

    with conn() as c, c.cursor() as cur:
        cur.execute(
            """
            INSERT INTO regime_history (date, regime, confidence, transition_probs)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (date) DO UPDATE SET
                regime = EXCLUDED.regime,
                confidence = EXCLUDED.confidence,
                transition_probs = EXCLUDED.transition_probs
            """,
            (today, regime["label"], regime["confidence"], transition_probs_json),
        )

    log_activity(
        component="regime.detector",
        action="run_regime_pipeline",
        date=today,
        regime=regime["label"],
        confidence=regime["confidence"],
    )
    logger.info("regime_pipeline_complete", date=today, regime=regime["label"])
    return regime
