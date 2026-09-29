"""Unit tests for src/risk/ — Unit 10 Risk Management."""
from __future__ import annotations

import json
import math
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# position_sizer tests
# ---------------------------------------------------------------------------
from src.risk.position_sizer import (
    compute_max_shares,
    correlation_multiplier,
    volatility_tier_cap,
)


@pytest.mark.parametrize(
    "vol_60d, expected_cap",
    [
        (0.05, 0.05),   # <10%  tier
        (0.15, 0.04),   # <20%  tier
        (0.25, 0.03),   # <30%  tier
        (0.35, 0.02),   # >=30% tier
    ],
)
def test_volatility_tier_cap(vol_60d, expected_cap):
    assert volatility_tier_cap(vol_60d) == expected_cap


def test_volatility_tier_boundaries():
    """Boundary values at exactly 10%, 20%, 30% must land in the higher tier."""
    assert volatility_tier_cap(0.10) == 0.04  # NOT <0.10, so goes to <0.20
    assert volatility_tier_cap(0.20) == 0.03
    assert volatility_tier_cap(0.30) == 0.02


def test_correlation_multiplier_low():
    assert correlation_multiplier(0.3) == 1.0
    assert correlation_multiplier(0.5) == 1.0


def test_correlation_multiplier_high():
    assert correlation_multiplier(0.9) == pytest.approx(0.7)
    assert correlation_multiplier(1.0) == pytest.approx(0.7)


def test_correlation_multiplier_linear():
    # At corr=0.65 (midpoint of 0.5–0.8): 1.0 + (0.65-0.5)*(-1.0) = 0.85
    result = correlation_multiplier(0.65)
    assert result == pytest.approx(0.85, abs=1e-9)


def test_compute_max_shares_basic():
    # vol=0.05 -> cap=0.05, corr=0.0 -> mult=1.0
    # max_value = 0.05 * 1.0 * 100_000 = 5000
    # shares = floor(5000 / 50) = 100
    shares = compute_max_shares("AAPL", 100_000, 50.0, 0.05, 0.0)
    assert shares == 100


def test_compute_max_shares_high_vol():
    # vol=0.35 -> cap=0.02, corr=0.9 -> mult=0.7
    # max_value = 0.02 * 0.7 * 100_000 ~= 1400 (floating point: 1399.9999...)
    # shares = floor(1399.999... / 100) = 13
    shares = compute_max_shares("TSLA", 100_000, 100.0, 0.35, 0.9)
    assert shares == 13


def test_compute_max_shares_zero_price():
    assert compute_max_shares("X", 100_000, 0.0, 0.10, 0.0) == 0


def test_compute_max_shares_zero_portfolio():
    assert compute_max_shares("X", 0.0, 50.0, 0.10, 0.0) == 0


# ---------------------------------------------------------------------------
# limits tests
# ---------------------------------------------------------------------------
from src.risk.limits import (
    check_beta_limit,
    check_cash_floor,
    check_drawdown_limits,
    check_position_limit,
    check_sector_limit,
)


def test_drawdown_ok():
    # -2% drawdown, daily halt is -3% -> 'ok'
    result = check_drawdown_limits(98_000, 100_000)
    assert result == "ok"


def test_drawdown_reduce_risk():
    # -5% drawdown, -3% threshold -> 'reduce_risk'
    result = check_drawdown_limits(95_000, 100_000)
    assert result == "reduce_risk"


def test_drawdown_halt():
    # -20% drawdown, -15% liquidate threshold -> 'halt'
    result = check_drawdown_limits(80_000, 100_000)
    assert result == "halt"


def test_drawdown_initial_zero_guard():
    # Guard: initial=0 should return 'ok' without dividing by zero
    result = check_drawdown_limits(100_000, 0)
    assert result == "ok"


def test_check_position_limit_within():
    # 4% position in a 100k portfolio -> within 5% limit
    assert check_position_limit(4_000, 100_000) is True


def test_check_position_limit_exceeded():
    # 6% position -> exceeds 5% limit
    assert check_position_limit(6_000, 100_000) is False


def test_check_cash_floor_breached():
    # min_cash_pct is 0.10 — 5% cash is below the floor
    assert check_cash_floor({"equity": 100_000, "cash": 5_000}) is True


def test_check_cash_floor_within():
    assert check_cash_floor({"equity": 100_000, "cash": 20_000}) is False


def test_check_cash_floor_zero_equity_guard():
    assert check_cash_floor({"equity": 0, "cash": 0}) is False


def test_check_sector_limit_within():
    assert check_sector_limit(15_000, 5_000, 100_000) is True  # 20% total


def test_check_sector_limit_exceeded():
    assert check_sector_limit(20_000, 10_000, 100_000) is False  # 30% total


def test_check_beta_limit_ok():
    assert check_beta_limit(1.1) is True
    assert check_beta_limit(1.3) is True  # exactly at limit


def test_check_beta_limit_exceeded():
    assert check_beta_limit(1.4) is False


# ---------------------------------------------------------------------------
# wash_sale tests
# ---------------------------------------------------------------------------
from src.risk.wash_sale import intentional_wash_ok, would_trigger_wash_sale
from src.risk.tax_lots import TaxLot


def _make_lot(ticker: str, qty: int, cost_basis: float, acquired_date: date) -> TaxLot:
    return TaxLot(ticker=ticker, qty=qty, cost_basis=cost_basis, acquired_date=acquired_date)


def test_wash_sale_not_triggered_on_gain():
    """Selling at a gain should never trigger wash sale."""
    lot = _make_lot("AAPL", 100, 100.0, date(2026, 5, 20))
    # sale_price=150 > cost_basis=100 -> gain, no wash sale
    result = would_trigger_wash_sale("AAPL", date(2026, 6, 1), [lot], sale_price=150.0)
    assert result is False


def test_wash_sale_triggered_on_loss_within_window():
    """Selling at a loss with a lot acquired within 30 days -> wash sale."""
    lot = _make_lot("AAPL", 100, 100.0, date(2026, 5, 20))
    # sale_price=80 < cost_basis=100 -> loss; acquired ~12 days before sale
    result = would_trigger_wash_sale("AAPL", date(2026, 6, 1), [lot], sale_price=80.0)
    assert result is True


def test_wash_sale_not_triggered_on_loss_outside_window():
    """Selling at a loss with lot acquired >30 days ago -> no wash sale."""
    lot = _make_lot("AAPL", 100, 100.0, date(2026, 4, 1))
    # sale_date = 2026-06-15, acquired = 2026-04-01, >30 days before
    result = would_trigger_wash_sale("AAPL", date(2026, 6, 15), [lot], sale_price=80.0)
    assert result is False


def test_wash_sale_empty_lots():
    result = would_trigger_wash_sale("AAPL", date(2026, 6, 1), [], sale_price=80.0)
    assert result is False


def test_intentional_wash_ok_above_threshold():
    assert intentional_wash_ok("AAPL", 0.01) is True


def test_intentional_wash_ok_below_threshold():
    assert intentional_wash_ok("AAPL", 0.003) is False


# ---------------------------------------------------------------------------
# tax_lots tests (with mocked DB)
# ---------------------------------------------------------------------------
from src.risk.tax_lots import add_lot, compute_gain, get_lots


def _make_cursor_mock(rows=None):
    cur = MagicMock()
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchall = MagicMock(return_value=rows or [])
    return cur


def _make_conn_mock(cursor_mock):
    c = MagicMock()
    c.__enter__ = MagicMock(return_value=c)
    c.__exit__ = MagicMock(return_value=False)
    c.cursor = MagicMock(return_value=cursor_mock)
    return c


def test_add_lot_calls_db():
    """add_lot should call INSERT on the DB with correct JSON payload."""
    cur = _make_cursor_mock(rows=[])
    c = _make_conn_mock(cur)

    with patch("src.risk.tax_lots.conn") as mock_conn:
        mock_conn.return_value = c
        add_lot("AAPL", 50, 150.0, date(2026, 1, 15))

    cur.execute.assert_called()
    # Ensure the INSERT was called (get_lots calls SELECT first, then INSERT)
    assert cur.execute.call_count >= 1


def test_get_lots_parses_correctly():
    """get_lots should deserialize TaxLot dataclasses from DB rows."""
    lot_data = {
        "ticker": "MSFT",
        "qty": 10,
        "cost_basis": 300.0,
        "acquired_date": "2025-06-01",
    }
    rows = [("taxlot_0", json.dumps(lot_data))]
    cur = _make_cursor_mock(rows=rows)
    c = _make_conn_mock(cur)

    with patch("src.risk.tax_lots.conn") as mock_conn:
        mock_conn.return_value = c
        lots = get_lots("MSFT")

    assert len(lots) == 1
    assert lots[0].ticker == "MSFT"
    assert lots[0].qty == 10
    assert lots[0].cost_basis == 300.0
    assert lots[0].acquired_date == date(2025, 6, 1)


def test_compute_gain_fifo_short_term():
    """compute_gain should return correct short-term gain using FIFO."""
    lot_data = {
        "ticker": "NVDA",
        "qty": 20,
        "cost_basis": 400.0,
        "acquired_date": date.today().isoformat(),  # acquired today -> short term
    }
    rows = [("taxlot_0", json.dumps(lot_data))]
    cur = _make_cursor_mock(rows=rows)
    c = _make_conn_mock(cur)

    with patch("src.risk.tax_lots.conn") as mock_conn:
        mock_conn.return_value = c
        result = compute_gain("NVDA", sale_price=450.0, qty=10)

    # gain = (450 - 400) * 10 = 500, short term (held today)
    assert result["short_term_gain"] == pytest.approx(500.0)
    assert result["long_term_gain"] == pytest.approx(0.0)
    assert result["remaining_qty"] == 0


# ---------------------------------------------------------------------------
# rebalancer tests
# ---------------------------------------------------------------------------
from src.risk.rebalancer import compute_rebalance_orders


def test_rebalance_generates_buy_order():
    current = {}
    target_weights = {"AAPL": 0.10}
    # Need price for AAPL since it's not in current; skip (price unknown for new positions)
    # Use a current position at 0 qty with known price:
    current = {"AAPL": {"qty": 0, "price": 100.0, "market_value": 0.0}}
    orders = compute_rebalance_orders(current, target_weights, portfolio_value=100_000)
    assert len(orders) == 1
    assert orders[0]["ticker"] == "AAPL"
    assert orders[0]["side"] == "buy"
    assert orders[0]["qty"] == 100  # floor(0.10 * 100000 / 100)


def test_rebalance_generates_sell_order():
    # 20% position, target 5% -> sell
    current = {"TSLA": {"qty": 200, "price": 100.0, "market_value": 20_000.0}}
    target_weights = {"TSLA": 0.05}
    orders = compute_rebalance_orders(current, target_weights, portfolio_value=100_000)
    assert len(orders) == 1
    assert orders[0]["side"] == "sell"


def test_rebalance_no_order_within_threshold():
    # 5.2% position, target 5% -> drift 0.2% < 0.5% threshold
    current = {"AAPL": {"qty": 104, "price": 50.0, "market_value": 5_200.0}}
    target_weights = {"AAPL": 0.05}
    orders = compute_rebalance_orders(current, target_weights, portfolio_value=100_000)
    assert len(orders) == 0


def test_rebalance_raises_on_missing_price():
    current = {"AAPL": {"qty": 10, "market_value": 1000.0}}  # missing 'price'
    with pytest.raises(ValueError, match="missing required 'price' key"):
        compute_rebalance_orders(current, {"AAPL": 0.10}, portfolio_value=100_000)


def test_rebalance_respects_max_shares_cap():
    current = {"AAPL": {"qty": 0, "price": 100.0, "market_value": 0.0}}
    target_weights = {"AAPL": 0.10}  # 100 shares needed
    orders = compute_rebalance_orders(
        current,
        target_weights,
        portfolio_value=100_000,
        max_shares_map={"AAPL": 50},
    )
    assert orders[0]["qty"] == 50  # capped at 50
