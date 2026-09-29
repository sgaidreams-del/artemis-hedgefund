"""Gymnasium environment for portfolio allocation RL agent."""
from __future__ import annotations

import numpy as np
import gymnasium as gym
from gymnasium import spaces
from dataclasses import dataclass

from src.core.logging import get_logger
from src.strategy.rl.reward import compute_reward

log = get_logger(__name__)


@dataclass
class PortfolioState:
    equity_alloc: float      # current equity allocation (0-1)
    avg_momentum: float      # average momentum score across holdings (-1 to 1)
    avg_vol: float           # average 20d volatility
    current_drawdown: float  # current drawdown (negative number)
    regime_id: int           # 0-4


class PortfolioEnv(gym.Env):
    """5D continuous action space: [equity_alloc, concentration_factor, momentum_tilt,
    size_tilt, rebalance_urgency] all in [0,1].
    5D observation space: same fields as PortfolioState.
    IMPORTANT: warmup = min(60, max(0, len(prices) - 10)) to avoid broken episodes on
    short price histories.
    """

    metadata = {"render_modes": []}

    def __init__(self, prices: "np.ndarray | None" = None, initial_value: float = 1_000_000.0):
        super().__init__()

        # Action space: 5D continuous [0, 1]
        self.action_space = spaces.Box(
            low=np.zeros(5, dtype=np.float32),
            high=np.ones(5, dtype=np.float32),
            dtype=np.float32,
        )

        # Observation space: [equity_alloc, avg_momentum, avg_vol, current_drawdown, regime_id]
        # equity_alloc: [0, 1], avg_momentum: [-1, 1], avg_vol: [0, 5],
        # current_drawdown: [-1, 0], regime_id: [0, 4]
        self.observation_space = spaces.Box(
            low=np.array([0.0, -1.0, 0.0, -1.0, 0.0], dtype=np.float32),
            high=np.array([1.0, 1.0, 5.0, 0.0, 4.0], dtype=np.float32),
            dtype=np.float32,
        )

        if prices is None:
            # Default synthetic price series
            rng = np.random.default_rng(42)
            prices = 100.0 * np.exp(np.cumsum(rng.normal(0.0005, 0.015, 252)))

        self.prices = np.asarray(prices, dtype=np.float64)
        self.initial_value = initial_value
        self.warmup = min(60, max(0, len(self.prices) - 10))

        self._step_idx: int = 0
        self._portfolio_value: float = initial_value
        self._peak_value: float = initial_value
        self._state: PortfolioState | None = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_state(self, step_idx: int, equity_alloc: float = 0.6) -> PortfolioState:
        """Derive a PortfolioState from the price series at a given step."""
        idx = min(step_idx, len(self.prices) - 1)

        # avg_momentum: normalised 20-day return, clipped to [-1, 1]
        lookback = min(20, idx)
        if lookback > 0 and self.prices[idx - lookback] > 0:
            raw_ret = (self.prices[idx] / self.prices[idx - lookback]) - 1.0
        else:
            raw_ret = 0.0
        avg_momentum = float(np.clip(raw_ret * 10, -1.0, 1.0))

        # avg_vol: rolling 20-day std of log-returns
        start = max(0, idx - 20)
        window = self.prices[start : idx + 1]
        if len(window) >= 2:
            log_rets = np.diff(np.log(window))
            avg_vol = float(np.std(log_rets) * np.sqrt(252))
        else:
            avg_vol = 0.15

        # current_drawdown: relative to peak_value
        dd = (self._portfolio_value - self._peak_value) / max(self._peak_value, 1e-9)
        current_drawdown = float(np.clip(dd, -1.0, 0.0))

        # regime_id: simple momentum-based bucketing (0-4)
        if avg_momentum > 0.6:
            regime_id = 0  # strong bull
        elif avg_momentum > 0.2:
            regime_id = 1  # bull
        elif avg_momentum > -0.2:
            regime_id = 2  # sideways
        elif avg_momentum > -0.6:
            regime_id = 3  # bear
        else:
            regime_id = 4  # strong bear

        return PortfolioState(
            equity_alloc=float(np.clip(equity_alloc, 0.0, 1.0)),
            avg_momentum=avg_momentum,
            avg_vol=avg_vol,
            current_drawdown=current_drawdown,
            regime_id=regime_id,
        )

    def _state_to_obs(self, state: PortfolioState) -> np.ndarray:
        return np.array(
            [
                state.equity_alloc,
                state.avg_momentum,
                state.avg_vol,
                state.current_drawdown,
                float(state.regime_id),
            ],
            dtype=np.float32,
        )

    # ------------------------------------------------------------------
    # Gym interface
    # ------------------------------------------------------------------

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self._step_idx = self.warmup
        self._portfolio_value = self.initial_value
        self._peak_value = self.initial_value
        self._state = self._compute_state(self._step_idx, equity_alloc=0.6)
        obs = self._state_to_obs(self._state)
        info: dict = {}
        return obs, info

    def step(self, action):
        action = np.asarray(action, dtype=np.float32)
        action = np.clip(action, 0.0, 1.0)

        prev_value = self._portfolio_value

        # Advance the simulation by one step
        self._step_idx += 1
        at_end = self._step_idx >= len(self.prices) - 1

        # Update portfolio value using price return scaled by equity allocation
        if self._step_idx > 0 and self.prices[self._step_idx - 1] > 0:
            price_return = (
                self.prices[self._step_idx] / self.prices[self._step_idx - 1] - 1.0
            )
        else:
            price_return = 0.0

        equity_alloc = float(action[0])  # action[0] = equity_alloc
        self._portfolio_value *= 1.0 + equity_alloc * price_return

        # Update peak for drawdown tracking
        if self._portfolio_value > self._peak_value:
            self._peak_value = self._portfolio_value

        # Derive new state
        self._state = self._compute_state(self._step_idx, equity_alloc=equity_alloc)
        obs = self._state_to_obs(self._state)

        # Compute reward
        dd = self._state.current_drawdown
        reward = compute_reward(
            prev_value=prev_value,
            new_value=self._portfolio_value,
            drawdown=dd,
            action=action,
        )

        terminated = at_end
        truncated = False
        info = {
            "portfolio_value": self._portfolio_value,
            "step_idx": self._step_idx,
        }

        return obs, float(reward), terminated, truncated, info
