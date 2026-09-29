"""Phase 5 — exposure, Greeks, and per-underlying concentration caps."""
import pytest

from src.risk.limits import (
    check_exposure_limits,
    check_greeks_limits,
    check_underlying_concentration,
)


# ── Gross exposure / leverage ─────────────────────────────────────────────────

def test_exposure_within_cap():
    positions = [{"market_value": 40_000}, {"market_value": -30_000}]
    account = {"equity": 100_000}
    assert check_exposure_limits(positions, account) is False


def test_exposure_breaches_cap():
    # gross = |60k| + |60k| = 120k on 100k equity = 1.2x, over the 1.0 cap
    positions = [{"market_value": 60_000}, {"market_value": -60_000}]
    account = {"equity": 100_000}
    assert check_exposure_limits(positions, account) is True


def test_exposure_zero_equity_does_not_trip():
    assert check_exposure_limits([{"market_value": 1000}], {"equity": 0}) is False


# ── Greeks (delta-equivalent exposure) ────────────────────────────────────────

def test_greeks_within_cap():
    # 10% of portfolio, cap is 20%
    assert check_greeks_limits(delta_exposure=10_000, portfolio_value=100_000) is False


def test_greeks_breaches_cap():
    # 30% of portfolio, over the 20% cap
    assert check_greeks_limits(delta_exposure=30_000, portfolio_value=100_000) is True


def test_greeks_negative_delta_uses_magnitude():
    assert check_greeks_limits(delta_exposure=-30_000, portfolio_value=100_000) is True


def test_greeks_unknown_portfolio_value_fails_closed():
    # Per-order gate — unlike the portfolio-level halts, unknown data blocks.
    assert check_greeks_limits(delta_exposure=0.0, portfolio_value=0.0) is True


# ── Per-underlying concentration ──────────────────────────────────────────────

def test_underlying_concentration_within_cap():
    # existing 2k + new 1k = 3k on 100k = 3%, cap is 5%
    assert check_underlying_concentration(2_000, 1_000, 100_000) is False


def test_underlying_concentration_breaches_cap():
    # existing 4k + new 2k = 6k on 100k = 6%, over the 5% cap
    assert check_underlying_concentration(4_000, 2_000, 100_000) is True


def test_underlying_concentration_zero_portfolio_fails_closed():
    assert check_underlying_concentration(0, 100, 0) is True
