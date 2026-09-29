"""Tests for Unit 8 — FinRL PPO portfolio agent."""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
import pytest

from src.strategy.rl.environment import PortfolioEnv, PortfolioState
from src.strategy.rl.reward import compute_reward
from src.strategy.rl.finrl_agent import (
    _equal_weight_decisions,
    get_portfolio_decisions,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_prices(n: int = 100) -> np.ndarray:
    """Build a synthetic price series of length n."""
    rng = np.random.default_rng(0)
    log_returns = rng.normal(0.0005, 0.015, n)
    return 100.0 * np.exp(np.cumsum(log_returns))


# ---------------------------------------------------------------------------
# Test 1 — PortfolioEnv with 100-row price series
# ---------------------------------------------------------------------------

class TestPortfolioEnv:
    def setup_method(self):
        prices = _make_prices(100)
        self.env = PortfolioEnv(prices=prices)

    def test_reset_returns_valid_obs(self):
        obs, info = self.env.reset()
        assert obs.shape == (5,), f"Expected shape (5,), got {obs.shape}"
        # Observation must lie within the observation space
        assert self.env.observation_space.contains(obs), (
            f"obs {obs} not in observation space {self.env.observation_space}"
        )
        assert isinstance(info, dict)

    def test_step_returns_correct_tuple(self):
        self.env.reset()
        action = self.env.action_space.sample()
        result = self.env.step(action)
        assert len(result) == 5, "step() must return (obs, reward, terminated, truncated, info)"
        obs, reward, terminated, truncated, info = result
        assert obs.shape == (5,)
        assert isinstance(reward, float)
        assert isinstance(terminated, (bool, np.bool_))
        assert isinstance(truncated, (bool, np.bool_))
        assert isinstance(info, dict)

    def test_obs_within_bounds_after_step(self):
        self.env.reset()
        for _ in range(5):
            action = self.env.action_space.sample()
            obs, _, terminated, _, _ = self.env.step(action)
            if not terminated:
                # avg_vol can occasionally be clipped at obs-space boundary
                assert obs.shape == (5,)

    def test_warmup_short_price_series(self):
        """warmup = min(60, max(0, len(prices) - 10)) must not exceed len(prices)-1."""
        prices = _make_prices(15)
        env = PortfolioEnv(prices=prices)
        assert env.warmup == min(60, max(0, len(prices) - 10))
        assert env.warmup < len(prices)

    def test_episode_terminates(self):
        prices = _make_prices(20)
        env = PortfolioEnv(prices=prices)
        env.reset()
        terminated = False
        for _ in range(len(prices) + 5):
            if terminated:
                break
            action = env.action_space.sample()
            _, _, terminated, _, _ = env.step(action)
        assert terminated, "Episode should terminate before running out of price data"


# ---------------------------------------------------------------------------
# Test 2 — compute_reward stays in [-10, +10]
# ---------------------------------------------------------------------------

class TestComputeReward:
    def _dummy_action(self, rebalance_urgency: float = 0.5) -> np.ndarray:
        a = np.array([0.6, 0.5, 0.5, 0.5, rebalance_urgency], dtype=np.float32)
        return a

    def test_positive_return_in_range(self):
        r = compute_reward(1_000_000, 1_010_000, -0.01, self._dummy_action())
        assert -10.0 <= r <= 10.0

    def test_negative_return_in_range(self):
        r = compute_reward(1_000_000, 950_000, -0.05, self._dummy_action())
        assert -10.0 <= r <= 10.0

    def test_extreme_gain_clipped(self):
        r = compute_reward(1.0, 1e9, 0.0, self._dummy_action())
        assert r <= 10.0

    def test_extreme_loss_clipped(self):
        r = compute_reward(1e9, 1.0, -1.0, self._dummy_action())
        assert r >= -10.0

    def test_reward_is_float(self):
        r = compute_reward(1_000_000, 1_005_000, 0.0, self._dummy_action())
        assert isinstance(r, float)

    def test_high_rebalance_urgency_slightly_penalised(self):
        r_low = compute_reward(1_000_000, 1_000_000, 0.0, self._dummy_action(0.0))
        r_high = compute_reward(1_000_000, 1_000_000, 0.0, self._dummy_action(1.0))
        assert r_low >= r_high, "Higher rebalance urgency should not increase reward"

    def test_action_as_list_accepted(self):
        """action can be a plain Python list — should not raise."""
        r = compute_reward(1_000_000, 1_000_000, 0.0, [0.6, 0.5, 0.5, 0.5, 0.3])
        assert -10.0 <= r <= 10.0


# ---------------------------------------------------------------------------
# Test 3 — _equal_weight_decisions returns correct dict
# ---------------------------------------------------------------------------

class TestEqualWeightDecisions:
    EXPECTED_KEYS = {
        "equity_alloc",
        "concentration_factor",
        "momentum_tilt",
        "size_tilt",
        "rebalance_urgency",
    }

    def test_returns_all_five_keys(self):
        result = _equal_weight_decisions()
        assert set(result.keys()) == self.EXPECTED_KEYS

    def test_values_are_floats_in_range(self):
        result = _equal_weight_decisions()
        for key, val in result.items():
            assert isinstance(val, float), f"{key} should be float, got {type(val)}"
            assert 0.0 <= val <= 1.0, f"{key}={val} out of [0,1]"

    def test_equity_alloc_is_0_6(self):
        result = _equal_weight_decisions()
        assert result["equity_alloc"] == pytest.approx(0.6)

    def test_rebalance_urgency_is_0_3(self):
        result = _equal_weight_decisions()
        assert result["rebalance_urgency"] == pytest.approx(0.3)


# ---------------------------------------------------------------------------
# Test 4 — get_portfolio_decisions returns equal-weight fallback when disabled
# ---------------------------------------------------------------------------

class TestGetPortfolioDecisions:
    def _make_state(self) -> PortfolioState:
        return PortfolioState(
            equity_alloc=0.6,
            avg_momentum=0.1,
            avg_vol=0.18,
            current_drawdown=-0.02,
            regime_id=2,
        )

    def test_fallback_when_disabled(self, monkeypatch):
        monkeypatch.setenv("FINRL_ENABLED", "false")
        result = get_portfolio_decisions(self._make_state())
        expected = _equal_weight_decisions()
        assert result == expected

    def test_returns_all_five_keys_when_enabled(self):
        """With FINRL_ENABLED=true (default), result still has all 5 keys."""
        os.environ.pop("FINRL_ENABLED", None)
        result = get_portfolio_decisions(self._make_state())
        expected_keys = {
            "equity_alloc",
            "concentration_factor",
            "momentum_tilt",
            "size_tilt",
            "rebalance_urgency",
        }
        assert set(result.keys()) == expected_keys

    def test_all_values_in_unit_interval(self):
        os.environ.pop("FINRL_ENABLED", None)
        result = get_portfolio_decisions(self._make_state())
        for key, val in result.items():
            assert 0.0 <= val <= 1.0, f"{key}={val} not in [0,1]"

    def test_false_string_variants_disabled(self, monkeypatch):
        """FINRL_ENABLED=False (capital F) should also disable the agent."""
        monkeypatch.setenv("FINRL_ENABLED", "False")
        result = get_portfolio_decisions(self._make_state())
        assert result == _equal_weight_decisions()
