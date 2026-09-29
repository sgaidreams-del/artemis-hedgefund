"""FinRL PPO agent for portfolio allocation decisions."""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np

from src.core.logging import get_logger
from src.strategy.rl.environment import PortfolioEnv, PortfolioState

log = get_logger(__name__)

MODEL_PATH = Path(__file__).resolve().parents[3] / "models" / "finrl" / "model.zip"

# Module-level cache — avoids re-loading the model on every call
_agent_cache = None


def _is_enabled() -> bool:
    """Read FINRL_ENABLED at call time so os.environ changes after import work."""
    return os.environ.get("FINRL_ENABLED", "true").lower() != "false"


def _equal_weight_decisions() -> dict:
    """Fallback equal-weight portfolio decisions."""
    return {
        "equity_alloc": 0.6,
        "concentration_factor": 0.5,
        "momentum_tilt": 0.5,
        "size_tilt": 0.5,
        "rebalance_urgency": 0.3,
    }


def _decode_action(action) -> dict:
    """Convert 5D numpy array to named dict."""
    action = np.asarray(action, dtype=np.float64).flatten()
    return {
        "equity_alloc": float(np.clip(action[0], 0.0, 1.0)),
        "concentration_factor": float(np.clip(action[1], 0.0, 1.0)),
        "momentum_tilt": float(np.clip(action[2], 0.0, 1.0)),
        "size_tilt": float(np.clip(action[3], 0.0, 1.0)),
        "rebalance_urgency": float(np.clip(action[4], 0.0, 1.0)),
    }


def load_or_train_agent():
    """Load PPO model from MODEL_PATH if it exists.

    If the model file is missing, train a new PPO(MlpPolicy) for 10_000 steps
    and save to MODEL_PATH. Result is cached in the module-level _agent_cache.

    Returns:
        PPO model instance or None if an error occurs.
    """
    global _agent_cache

    if _agent_cache is not None:
        return _agent_cache

    try:
        from stable_baselines3 import PPO

        if MODEL_PATH.exists():
            log.info("finrl_agent.load", path=str(MODEL_PATH))
            env = PortfolioEnv()
            model = PPO.load(str(MODEL_PATH), env=env)
        else:
            log.info("finrl_agent.train", steps=10_000, path=str(MODEL_PATH))
            env = PortfolioEnv()
            model = PPO("MlpPolicy", env, verbose=0)
            model.learn(total_timesteps=10_000)
            MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
            model.save(str(MODEL_PATH))
            log.info("finrl_agent.saved", path=str(MODEL_PATH))

        _agent_cache = model
        return model

    except Exception as exc:
        log.error("finrl_agent.load_or_train.error", error=str(exc))
        return None


def get_portfolio_decisions(portfolio_state: PortfolioState) -> dict:
    """Produce portfolio allocation decisions from the RL agent.

    Checks _is_enabled() first. Loads/trains agent via module-level cache.
    Falls back to _equal_weight_decisions() if FINRL_ENABLED=false or any error.

    Args:
        portfolio_state: Current PortfolioState observation.

    Returns:
        Dict with keys: equity_alloc, concentration_factor, momentum_tilt,
        size_tilt, rebalance_urgency.
    """
    if not _is_enabled():
        log.info("finrl_agent.disabled")
        return _equal_weight_decisions()

    try:
        model = load_or_train_agent()
        if model is None:
            return _equal_weight_decisions()

        obs = np.array(
            [
                portfolio_state.equity_alloc,
                portfolio_state.avg_momentum,
                portfolio_state.avg_vol,
                portfolio_state.current_drawdown,
                float(portfolio_state.regime_id),
            ],
            dtype=np.float32,
        )

        action, _ = model.predict(obs, deterministic=True)
        return _decode_action(action)

    except Exception as exc:
        log.error("finrl_agent.get_portfolio_decisions.error", error=str(exc))
        return _equal_weight_decisions()
