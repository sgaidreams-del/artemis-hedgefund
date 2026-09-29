import pytest
import time
from unittest.mock import patch, MagicMock, call

from src.risk.pretrade import PreTradeDecision

# These tests isolate the escalation ladder; the pre-trade gate has its own
# dedicated suite (test_pretrade.py), so here we mock it as "allow".
_GATE_ALLOW = PreTradeDecision(allow=True, reason="ok")


def test_compute_slippage_buy_positive():
    """Paying more than expected = positive (unfavorable) slippage."""
    from src.execution.monitor import compute_slippage_bps
    slip = compute_slippage_bps(fill_price=100.10, expected_price=100.00, side="buy")
    assert slip == pytest.approx(10.0, abs=0.1)

def test_compute_slippage_sell_favorable():
    """Selling above expected = negative (favorable) slippage."""
    from src.execution.monitor import compute_slippage_bps
    slip = compute_slippage_bps(fill_price=100.10, expected_price=100.00, side="sell")
    assert slip == pytest.approx(-10.0, abs=0.1)

def test_compute_slippage_zero_price():
    from src.execution.monitor import compute_slippage_bps
    assert compute_slippage_bps(100.0, 0.0, "buy") == 0.0

def test_route_order_blocks_on_kill_switch():
    """route_order returns None when kill switch is paused."""
    from src.execution.order_router import route_order
    with patch("src.execution.order_router.is_paused", return_value=True):
        result = route_order("AAPL", "buy", 10, 150.0)
    assert result is None

def test_route_order_fills_on_step1():
    """If step 1 limit fills, returns result with escalation_step=1."""
    from src.execution.order_router import route_order
    mock_order = {"order_id": "abc123", "ticker": "AAPL", "side": "buy", "qty": 10, "limit_price": 150.0, "status": "accepted"}

    with patch("src.execution.order_router.is_paused", return_value=False), \
         patch("src.execution.order_router.check_equity_order", return_value=_GATE_ALLOW), \
         patch("src.execution.order_router.submit_limit_order", return_value=mock_order), \
         patch("src.execution.order_router._wait_for_fill", return_value=True), \
         patch("src.execution.order_router.get_filled_price", return_value=150.05):
        result = route_order("AAPL", "buy", 10, 150.0)

    assert result is not None
    assert result["escalation_step"] == 1
    assert result["fill_price"] == pytest.approx(150.05)

def test_route_order_escalates_to_step2():
    """If step 1 doesn't fill, escalates to step 2."""
    from src.execution.order_router import route_order
    mock_order = {"order_id": "abc123", "ticker": "AAPL", "side": "buy", "qty": 10, "limit_price": 150.0, "status": "accepted"}

    fill_sequence = [False, True]  # step1 no fill, step2 fill

    with patch("src.execution.order_router.is_paused", return_value=False), \
         patch("src.execution.order_router.check_equity_order", return_value=_GATE_ALLOW), \
         patch("src.execution.order_router.submit_limit_order", return_value=mock_order), \
         patch("src.execution.order_router._wait_for_fill", side_effect=fill_sequence), \
         patch("src.execution.order_router.cancel_order"), \
         patch("src.execution.order_router.get_filled_price", return_value=150.40):
        result = route_order("AAPL", "buy", 10, 150.0)

    assert result is not None
    assert result["escalation_step"] == 2

def test_route_order_returns_none_after_all_steps_fail():
    """Returns None if all 3 escalation steps fail to fill."""
    from src.execution.order_router import route_order
    mock_order = {"order_id": "abc123", "ticker": "AAPL", "side": "buy", "qty": 10, "limit_price": 150.0, "status": "accepted"}

    with patch("src.execution.order_router.is_paused", return_value=False), \
         patch("src.execution.order_router.check_equity_order", return_value=_GATE_ALLOW), \
         patch("src.execution.order_router.submit_limit_order", return_value=mock_order), \
         patch("src.execution.order_router._wait_for_fill", return_value=False), \
         patch("src.execution.order_router.cancel_order"), \
         patch("src.execution.order_router.get_order_status", return_value="canceled"), \
         patch("time.sleep"):
        result = route_order("AAPL", "buy", 10, 150.0)

    assert result is None

def test_log_trade_inserts_to_db():
    """log_trade should call INSERT on the trades table."""
    from src.execution.journal import log_trade

    # Build a mock that supports: with conn() as c, c.cursor() as cur:
    mock_cursor = MagicMock()
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)

    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = mock_cursor

    mock_conn_cm = MagicMock()
    mock_conn_cm.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn_cm.__exit__ = MagicMock(return_value=False)

    with patch("src.execution.journal.conn", return_value=mock_conn_cm):
        trade_id = log_trade(
            ticker="AAPL", side="buy", qty=10,
            order_type="limit", limit_price=150.0,
            fill_price=150.05, slippage_bps=3.3,
            signals={"technical_composite": 0.5},
            rationale="momentum signal"
        )

    assert isinstance(trade_id, str) and len(trade_id) == 36  # UUID
    mock_cursor.execute.assert_called_once()

def test_zero_qty_blocked():
    """submit_limit_order with qty=0 returns None without calling Alpaca."""
    from src.execution.broker import submit_limit_order
    with patch("src.execution.broker._trading_client") as mock_tc:
        result = submit_limit_order("AAPL", 0, "buy", 150.0)
    assert result is None
    mock_tc.assert_not_called()

def test_cancel_all_orders_calls_bulk_cancel():
    from src.execution.broker import cancel_all_orders
    mock_client = MagicMock()
    mock_client.cancel_orders.return_value = [MagicMock(), MagicMock()]
    with patch("src.execution.broker._trading_client", return_value=mock_client):
        count = cancel_all_orders()
    assert count == 2
    mock_client.cancel_orders.assert_called_once()

def test_cancel_all_orders_no_client_returns_zero():
    from src.execution.broker import cancel_all_orders
    with patch("src.execution.broker._trading_client", return_value=None):
        assert cancel_all_orders() == 0

def test_flatten_all_refuses_without_confirm():
    """flatten_all must not touch the broker unless confirm=True is explicit."""
    from src.execution.broker import flatten_all
    with patch("src.execution.broker._trading_client") as mock_tc:
        result = flatten_all()
    assert result == []
    mock_tc.assert_not_called()

def test_flatten_all_closes_positions_when_confirmed():
    from src.execution.broker import flatten_all
    mock_client = MagicMock()
    mock_resp = MagicMock(symbol="AAPL", status="ok")
    mock_client.close_all_positions.return_value = [mock_resp]
    with patch("src.execution.broker._trading_client", return_value=mock_client):
        result = flatten_all(confirm=True)
    assert result == [{"symbol": "AAPL", "status": "ok"}]
    mock_client.close_all_positions.assert_called_once_with(cancel_orders=True)

def test_get_open_orders_no_client_returns_empty():
    from src.execution.broker import get_open_orders
    with patch("src.execution.broker._trading_client", return_value=None):
        assert get_open_orders() == []
