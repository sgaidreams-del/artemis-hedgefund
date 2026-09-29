"""Reward function for the portfolio RL environment."""
from __future__ import annotations

import numpy as np


def compute_reward(
    prev_value: float,
    new_value: float,
    drawdown: float,
    action,
) -> float:
    """Sortino-like reward: excess return - drawdown_penalty - turnover_penalty.

    Args:
        prev_value: Portfolio value before the step.
        new_value: Portfolio value after the step.
        drawdown: Current drawdown fraction (negative number, e.g. -0.05).
        action: 5-element array; action[4] is rebalance_urgency in [0, 1].

    Returns:
        Reward clipped to [-10, +10].
    """
    action = np.asarray(action, dtype=np.float64)

    # Step return
    if prev_value > 0:
        step_return = (new_value - prev_value) / prev_value
    else:
        step_return = 0.0

    # Scale to annualised basis (assuming daily steps, ~252 per year)
    annualised_return = step_return * 252.0

    # Downside penalty — penalise negative returns only (Sortino style)
    downside = min(step_return, 0.0) * 252.0
    sortino_term = annualised_return - abs(downside) * 2.0

    # Drawdown penalty — penalise being in a drawdown
    drawdown_penalty = abs(min(drawdown, 0.0)) * 5.0

    # Turnover penalty — high rebalance_urgency has a small cost
    rebalance_urgency = float(action[4])
    turnover_penalty = rebalance_urgency * 0.1

    reward = sortino_term - drawdown_penalty - turnover_penalty
    return float(np.clip(reward, -10.0, 10.0))
