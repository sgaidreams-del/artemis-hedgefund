"""Experiment runner — orchestrates sandbox → scorecard → journal upsert."""
from __future__ import annotations

import uuid

from src.core.logging import get_logger
from src.autoresearch.experiment.sandbox import create_sandbox_signals
from src.autoresearch.journal.manager import create_entry, update_entry

log = get_logger(__name__)


def _safe_import_scorecard():
    """Import scorecard lazily to avoid hard dependency at module load."""
    try:
        from src.validation import scorecard  # type: ignore[import]
        return scorecard
    except ImportError:
        return None


def _fallback_scorecard(signals_df) -> dict:
    """Compute a minimal scorecard from signals_df when the validation module is absent."""
    import numpy as np

    returns = signals_df["returns"].values
    n = len(returns)
    if n < 2:
        return {"sharpe": 0.0, "total_return": 0.0, "max_drawdown": 0.0, "status": "fallback"}

    mean_r = float(np.mean(returns))
    std_r = float(np.std(returns, ddof=1))
    sharpe = (mean_r / std_r * (252**0.5)) if std_r > 0 else 0.0

    cum = (1 + signals_df["returns"]).cumprod()
    total_return = float(cum.iloc[-1] - 1)
    rolling_max = cum.cummax()
    drawdown = (cum - rolling_max) / rolling_max
    max_dd = float(drawdown.min())

    return {
        "sharpe": round(sharpe, 4),
        "total_return": round(total_return, 4),
        "max_drawdown": round(max_dd, 4),
        "status": "fallback",
    }


def run_experiment(hypothesis: dict) -> dict:
    """Create experiment_id (uuid4). Build signals via sandbox.

    Import and call scorecard.run_full_validation() from src.validation.scorecard.
    Upsert to research_journal.

    Returns {experiment_id, hypothesis, scorecard_result}.
    """
    experiment_id = str(uuid.uuid4())
    hypothesis_id = hypothesis.get("id", "unknown")

    log.info("run_experiment_start", experiment_id=experiment_id, hypothesis_id=hypothesis_id)

    # Build synthetic signals
    signals_df = create_sandbox_signals(hypothesis)

    # Run scorecard
    scorecard_mod = _safe_import_scorecard()
    if scorecard_mod is not None and hasattr(scorecard_mod, "run_full_validation"):
        try:
            scorecard_result = scorecard_mod.run_full_validation(signals_df)
        except Exception as exc:
            log.warning("scorecard_failed", error=str(exc))
            scorecard_result = _fallback_scorecard(signals_df)
    else:
        scorecard_result = _fallback_scorecard(signals_df)

    # Create journal entry
    try:
        create_entry(
            experiment_id=experiment_id,
            hypothesis_id=hypothesis_id,
            category=hypothesis.get("signal_type", "unknown"),
            description=hypothesis.get("title", hypothesis_id),
        )

        # Determine result string based on scorecard
        sharpe = scorecard_result.get("sharpe", 0.0)
        result = "PASS" if sharpe > 0.5 else "FAIL"

        update_entry(
            experiment_id=experiment_id,
            result=result,
            performance={
                "sharpe": scorecard_result.get("sharpe"),
                "total_return": scorecard_result.get("total_return"),
                "max_drawdown": scorecard_result.get("max_drawdown"),
            },
            validation=scorecard_result,
            learnings=f"Automated experiment run. Sharpe={sharpe:.4f}.",
        )
    except Exception as exc:
        log.warning("journal_upsert_failed", error=str(exc))

    result_payload = {
        "experiment_id": experiment_id,
        "hypothesis": hypothesis,
        "scorecard_result": scorecard_result,
    }
    log.info("run_experiment_done", experiment_id=experiment_id, sharpe=scorecard_result.get("sharpe"))
    return result_payload
