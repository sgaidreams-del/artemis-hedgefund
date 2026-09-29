"""Safeguard suite for the pre-trade gate — deliberately trips each check.

Per the risk feedback: "a paper/sim environment where you can deliberately
trip each safeguard and confirm it fires. Untested safeguards are decoration."
"""
import pytest
from unittest.mock import patch

from src.risk.pretrade import (
    OrderIntent,
    PreTradeDecision,
    RiskConfigError,
    make_client_order_id,
    pretrade_check,
    validate_risk_config,
    _reset_rate_limiter,
)


@pytest.fixture(autouse=True)
def _isolate():
    """Each test starts with a clean rate limiter, kill switch off, and a
    fresh idempotency claim (so the deterministic id doesn't collide)."""
    _reset_rate_limiter()
    with patch("src.risk.pretrade.is_paused", return_value=False), \
         patch("src.risk.pretrade._claim_idempotency", return_value=True):
        yield


def _order(**kw):
    base = dict(symbol="AAPL", side="buy", qty=10, limit_price=200.0, asset_class="equity")
    base.update(kw)
    return OrderIntent(**base)


def _check(order=None, **kw):
    """pretrade_check with sane fresh-quote defaults, override anything via kw."""
    order = order or _order()
    defaults = dict(reference_price=200.0, market_open=True, now=1000.0, quote_age_seconds=10.0)
    defaults.update(kw)
    return pretrade_check(order, **defaults)


# ── A clean order passes ──────────────────────────────────────────────────────

def test_clean_order_allowed():
    d = _check()
    assert d.allow, d.reason


# ── Each safeguard trips ──────────────────────────────────────────────────────

def test_kill_switch_blocks():
    with patch("src.risk.pretrade.is_paused", return_value=True):
        d = _check()
    assert not d.allow
    assert "kill_switch" in d.reason


def test_zero_qty_rejected():
    d = _check(_order(qty=0))
    assert not d.allow
    assert "qty_valid" in d.reason


def test_max_qty_rejected():
    d = _check(_order(qty=999999))
    assert not d.allow
    assert "max_qty" in d.reason


def test_max_notional_rejected():
    # 10 shares * $50,000 = $500k, over the $25k cap
    d = _check(_order(qty=10, limit_price=50000.0), reference_price=50000.0)
    assert not d.allow
    assert "max_notional" in d.reason


def test_price_collar_rejects_far_limit():
    # limit 200 vs reference 100 = 100% deviation, way past 5%
    d = _check(_order(limit_price=200.0), reference_price=100.0)
    assert not d.allow
    assert "price_collar" in d.reason


def test_price_collar_equity_no_reference_fails_closed():
    d = _check(reference_price=None)
    assert not d.allow
    assert "price_collar" in d.reason


def test_data_staleness_rejects_old_quote():
    d = _check(quote_age_seconds=120.0)  # cap is 60s
    assert not d.allow
    assert "data_staleness" in d.reason


def test_data_staleness_equity_unknown_age_fails_closed():
    d = _check(quote_age_seconds=None)
    assert not d.allow
    assert "data_staleness" in d.reason


def test_market_closed_rejected():
    d = _check(market_open=False)
    assert not d.allow
    assert "market_hours" in d.reason


def test_market_clock_unavailable_fails_closed():
    d = _check(market_open=None)
    assert not d.allow
    assert "market_hours" in d.reason


def test_rate_limit_trips_after_cap():
    # default cap is 30/min; 31st within the same window should fail
    last = None
    for i in range(31):
        last = _check(_order(qty=10 + i))
    assert not last.allow
    assert "rate_limit" in last.reason


# ── Idempotency ───────────────────────────────────────────────────────────────

def test_duplicate_order_rejected():
    # Real claim logic: first claim True, second False
    with patch("src.risk.pretrade._claim_idempotency", side_effect=[True, False]):
        d1 = _check()
        d2 = _check(now=1001.0)
    assert d1.allow
    assert not d2.allow
    assert "idempotency" in d2.reason


def test_idempotency_not_consumed_when_other_check_fails():
    # If an earlier check fails, idempotency must be skipped (not recorded),
    # so a corrected resend can still go through.
    with patch("src.risk.pretrade._claim_idempotency") as claim:
        d = _check(_order(qty=0))
    assert not d.allow
    claim.assert_not_called()


def test_deterministic_client_order_id_stable():
    a = make_client_order_id(_order())
    b = make_client_order_id(_order())
    assert a == b and a.startswith("art-")


# ── Options path: collar deferred, every other check still applies ───────────

def test_option_collar_skipped_but_kill_switch_still_applies():
    opt = OrderIntent(symbol="AAPL  250117C00150000", side="buy", qty=1,
                      limit_price=5.0, asset_class="option")
    # No reference → equity would fail closed, option skips collar + staleness
    d = _check(opt, reference_price=None, quote_age_seconds=None)
    assert d.allow, d.reason
    # but kill switch still blocks it
    with patch("src.risk.pretrade.is_paused", return_value=True):
        d2 = _check(opt, reference_price=None, quote_age_seconds=None, now=1001.0)
    assert not d2.allow and "kill_switch" in d2.reason


def test_option_underlying_parsed_from_occ():
    opt = OrderIntent(symbol="AAPL  250117C00150000", side="buy", qty=1,
                      limit_price=5.0, asset_class="option")
    assert opt.underlying == "AAPL"


# ── Startup config validation ─────────────────────────────────────────────────

def test_valid_config_passes():
    validate_risk_config()  # the real settings.yaml should be valid


def test_missing_limit_crashes_loudly():
    bad = {
        "portfolio": {"max_position_pct": 0.05, "min_cash_pct": 0.10, "max_gross_leverage": 1.0},
        "risk": {"daily_drawdown_halt": -0.03, "max_drawdown_liquidate": -0.15,
                 "breach_behavior": "freeze", "consecutive_loss_days_halt": 3,
                 "max_delta_exposure_pct": 0.20},
        "execution": {"max_order_qty": 1000, "max_order_notional": 25000,
                      "price_collar_pct": 0.05, "max_quote_age_seconds": 60},  # max_orders_per_minute missing
    }
    with patch("src.risk.pretrade.settings", return_value=bad):
        with pytest.raises(RiskConfigError):
            validate_risk_config()


def test_absurd_limit_crashes_loudly():
    bad = {
        "portfolio": {"max_position_pct": 5.0, "min_cash_pct": 0.10, "max_gross_leverage": 1.0},  # 500% — absurd
        "risk": {"daily_drawdown_halt": -0.03, "max_drawdown_liquidate": -0.15,
                 "breach_behavior": "freeze", "consecutive_loss_days_halt": 3,
                 "max_delta_exposure_pct": 0.20},
        "execution": {"max_order_qty": 1000, "max_order_notional": 25000,
                      "price_collar_pct": 0.05, "max_orders_per_minute": 30,
                      "max_quote_age_seconds": 60},
    }
    with patch("src.risk.pretrade.settings", return_value=bad):
        with pytest.raises(RiskConfigError):
            validate_risk_config()
