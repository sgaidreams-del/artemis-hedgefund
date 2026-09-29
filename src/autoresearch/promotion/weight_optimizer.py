"""Weight optimizer — uses Optuna to maximize Sharpe ratio over signal weights."""
from __future__ import annotations

import math

from src.core.logging import get_logger

log = get_logger(__name__)


def _compute_portfolio_sharpe(weights: dict[str, float], performance_history: list[dict]) -> float:
    """Compute weighted average Sharpe from performance history.

    Each performance record should contain 'signal_name' and 'sharpe'.
    Returns weighted average Sharpe (proxy for portfolio Sharpe).
    """
    total_weight = 0.0
    weighted_sharpe = 0.0
    for record in performance_history:
        name = record.get("signal_name", "")
        sharpe = record.get("sharpe", 0.0)
        weight = weights.get(name, 0.0)
        if not math.isfinite(sharpe):
            sharpe = 0.0
        weighted_sharpe += weight * sharpe
        total_weight += weight

    if total_weight == 0:
        return 0.0
    return weighted_sharpe / total_weight


def optimize_weights(performance_history: list[dict]) -> dict:
    """Run an Optuna study minimizing negative Sharpe.

    Returns {signal_name: weight} with weights summing to 1.0.
    """
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)

    signal_names = list({r["signal_name"] for r in performance_history if "signal_name" in r})

    if not signal_names:
        log.warning("optimize_weights_no_signals")
        return {}

    if len(signal_names) == 1:
        return {signal_names[0]: 1.0}

    def objective(trial: optuna.Trial) -> float:
        raw_weights = {
            name: trial.suggest_float(name, 0.0, 1.0) for name in signal_names
        }
        total = sum(raw_weights.values())
        if total == 0:
            return 0.0
        weights = {k: v / total for k, v in raw_weights.items()}
        sharpe = _compute_portfolio_sharpe(weights, performance_history)
        return -sharpe  # minimize negative Sharpe

    study = optuna.create_study(direction="minimize")
    study.optimize(objective, n_trials=200, show_progress_bar=False)

    best_raw = study.best_params
    total = sum(best_raw.values())
    if total == 0:
        equal = 1.0 / len(signal_names)
        result = {name: equal for name in signal_names}
    else:
        result = {k: round(v / total, 6) for k, v in best_raw.items()}

    log.info("optimize_weights_done", weights=result, best_sharpe=-study.best_value)
    return result
