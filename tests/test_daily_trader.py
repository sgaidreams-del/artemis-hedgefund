from contextlib import ExitStack
from unittest.mock import patch, MagicMock


def _passing_gates():
    """ExitStack patching every halt/reconciliation check to 'no breach' —
    for tests that only care about the order-computation logic below them."""
    stack = ExitStack()
    stack.enter_context(patch("src.execution.daily_trader.check_daily_loss_halt", return_value=False))
    stack.enter_context(patch("src.execution.daily_trader.check_trailing_drawdown_halt", return_value=False))
    stack.enter_context(patch("src.execution.daily_trader.check_consecutive_loss_halt", return_value=False))
    stack.enter_context(patch("src.execution.daily_trader.check_cash_floor", return_value=False))
    stack.enter_context(patch("src.execution.daily_trader.check_exposure_limits", return_value=False))
    stack.enter_context(patch("src.execution.daily_trader.reconcile_options", return_value=[]))
    return stack


def test_run_daily_rebalance_blocks_on_kill_switch():
    from src.execution.daily_trader import run_daily_rebalance
    with patch("src.execution.daily_trader.is_paused", return_value=True):
        result = run_daily_rebalance()
    assert result["status"] == "paused"
    assert result["orders"] == []


def test_run_daily_rebalance_no_account():
    from src.execution.daily_trader import run_daily_rebalance
    with patch("src.execution.daily_trader.is_paused", return_value=False), \
         patch("src.execution.daily_trader.get_account", return_value=None):
        result = run_daily_rebalance()
    assert result["status"] == "no_account"


def test_run_daily_rebalance_daily_loss_halt():
    from src.execution.daily_trader import run_daily_rebalance
    account = {"equity": 50000.0, "cash": 50000.0}
    with patch("src.execution.daily_trader.is_paused", return_value=False), \
         patch("src.execution.daily_trader.get_account", return_value=account), \
         patch("src.execution.daily_trader.check_daily_loss_halt", return_value=True), \
         patch("src.execution.daily_trader.check_trailing_drawdown_halt", return_value=False), \
         patch("src.execution.daily_trader.check_consecutive_loss_halt", return_value=False), \
         patch("src.execution.daily_trader.check_cash_floor", return_value=False), \
         patch("src.execution.daily_trader.engage") as mock_engage:
        result = run_daily_rebalance()
    assert result["status"] == "halt"
    assert result["halt"] == "daily_loss_halt"
    mock_engage.assert_called_once()


def test_run_daily_rebalance_trailing_drawdown_halt():
    from src.execution.daily_trader import run_daily_rebalance
    account = {"equity": 50000.0, "cash": 50000.0}
    with patch("src.execution.daily_trader.is_paused", return_value=False), \
         patch("src.execution.daily_trader.get_account", return_value=account), \
         patch("src.execution.daily_trader.check_daily_loss_halt", return_value=False), \
         patch("src.execution.daily_trader.check_trailing_drawdown_halt", return_value=True), \
         patch("src.execution.daily_trader.check_consecutive_loss_halt", return_value=False), \
         patch("src.execution.daily_trader.check_cash_floor", return_value=False), \
         patch("src.execution.daily_trader.engage") as mock_engage:
        result = run_daily_rebalance()
    assert result["status"] == "halt"
    assert result["halt"] == "trailing_drawdown_halt"
    mock_engage.assert_called_once()


def test_run_daily_rebalance_consecutive_loss_halt():
    from src.execution.daily_trader import run_daily_rebalance
    account = {"equity": 50000.0, "cash": 50000.0}
    with patch("src.execution.daily_trader.is_paused", return_value=False), \
         patch("src.execution.daily_trader.get_account", return_value=account), \
         patch("src.execution.daily_trader.check_daily_loss_halt", return_value=False), \
         patch("src.execution.daily_trader.check_trailing_drawdown_halt", return_value=False), \
         patch("src.execution.daily_trader.check_consecutive_loss_halt", return_value=True), \
         patch("src.execution.daily_trader.check_cash_floor", return_value=False), \
         patch("src.execution.daily_trader.engage") as mock_engage:
        result = run_daily_rebalance()
    assert result["status"] == "halt"
    assert result["halt"] == "consecutive_loss_halt"
    mock_engage.assert_called_once()


def test_run_daily_rebalance_cash_floor_halt():
    from src.execution.daily_trader import run_daily_rebalance
    account = {"equity": 50000.0, "cash": 1000.0}
    with patch("src.execution.daily_trader.is_paused", return_value=False), \
         patch("src.execution.daily_trader.get_account", return_value=account), \
         patch("src.execution.daily_trader.check_daily_loss_halt", return_value=False), \
         patch("src.execution.daily_trader.check_trailing_drawdown_halt", return_value=False), \
         patch("src.execution.daily_trader.check_consecutive_loss_halt", return_value=False), \
         patch("src.execution.daily_trader.check_cash_floor", return_value=True), \
         patch("src.execution.daily_trader.engage") as mock_engage:
        result = run_daily_rebalance()
    assert result["status"] == "halt"
    assert result["halt"] == "cash_floor"
    mock_engage.assert_called_once()


def test_run_daily_rebalance_exposure_halt():
    from src.execution.daily_trader import run_daily_rebalance
    account = {"equity": 50000.0, "cash": 50000.0}
    with patch("src.execution.daily_trader.is_paused", return_value=False), \
         patch("src.execution.daily_trader.get_account", return_value=account), \
         patch("src.execution.daily_trader.get_positions", return_value=[]), \
         patch("src.execution.daily_trader.check_daily_loss_halt", return_value=False), \
         patch("src.execution.daily_trader.check_trailing_drawdown_halt", return_value=False), \
         patch("src.execution.daily_trader.check_consecutive_loss_halt", return_value=False), \
         patch("src.execution.daily_trader.check_cash_floor", return_value=False), \
         patch("src.execution.daily_trader.check_exposure_limits", return_value=True), \
         patch("src.execution.daily_trader.engage") as mock_engage:
        result = run_daily_rebalance()
    assert result["status"] == "halt"
    assert result["halt"] == "exposure_halt"
    mock_engage.assert_called_once()


def test_run_daily_rebalance_reconciliation_mismatch_skips_cycle():
    from src.execution.daily_trader import run_daily_rebalance
    account = {"equity": 100000.0, "cash": 100000.0}
    with patch("src.execution.daily_trader.is_paused", return_value=False), \
         patch("src.execution.daily_trader.get_account", return_value=account), \
         patch("src.execution.daily_trader.check_daily_loss_halt", return_value=False), \
         patch("src.execution.daily_trader.check_trailing_drawdown_halt", return_value=False), \
         patch("src.execution.daily_trader.check_consecutive_loss_halt", return_value=False), \
         patch("src.execution.daily_trader.check_cash_floor", return_value=False), \
         patch("src.execution.daily_trader.reconcile_options", return_value=["untracked_alpaca: AAPL250117C00150000"]):
        result = run_daily_rebalance()
    assert result["status"] == "reconciliation_mismatch"
    assert result["orders"] == []


def test_run_daily_rebalance_no_scores():
    from src.execution.daily_trader import run_daily_rebalance
    account = {"equity": 100000.0, "cash": 100000.0}
    with patch("src.execution.daily_trader.is_paused", return_value=False), \
         patch("src.execution.daily_trader.get_account", return_value=account), \
         _passing_gates(), \
         patch("src.execution.daily_trader._today_target_weights", return_value=({}, "unknown")):
        result = run_daily_rebalance()
    assert result["status"] == "no_scores"


def test_run_daily_rebalance_dry_run_does_not_submit():
    from src.execution.daily_trader import run_daily_rebalance
    account = {"equity": 100000.0, "cash": 60000.0}
    held = [{"ticker": "AAPL", "qty": 100, "avg_entry_price": 150.0,
             "current_price": 200.0, "market_value": 20000.0, "unrealized_pl": 5000.0}]
    target_weights = {"AAPL": 0.30, "MSFT": 0.10}
    orders = [
        {"ticker": "AAPL", "side": "buy", "qty": 50, "reason": "rebalance drift=+0.05"},
        {"ticker": "MSFT", "side": "buy", "qty": 20, "reason": "rebalance drift=+0.10"},
    ]
    with patch("src.execution.daily_trader.is_paused", return_value=False), \
         patch("src.execution.daily_trader.get_account", return_value=account), \
         _passing_gates(), \
         patch("src.execution.daily_trader._today_target_weights", return_value=(target_weights, "Bull/Low-Vol")), \
         patch("src.execution.daily_trader.get_positions", return_value=held), \
         patch("src.execution.daily_trader.get_latest_price", return_value=300.0), \
         patch("src.execution.daily_trader.compute_portfolio_correlation", return_value=0.3), \
         patch("src.execution.daily_trader._get_vol_60d", return_value=0.15), \
         patch("src.execution.daily_trader.compute_max_shares", return_value=1000), \
         patch("src.execution.daily_trader.compute_rebalance_orders", return_value=orders), \
         patch("src.execution.daily_trader.check_position_limit", return_value=True), \
         patch("src.execution.daily_trader.log_decision", return_value=1), \
         patch("src.execution.daily_trader.route_order") as mock_route:
        result = run_daily_rebalance(dry_run=True)

    assert result["status"] == "ok"
    assert result["dry_run"] is True
    assert len(result["orders"]) == 2
    assert all(o["submitted"] is False for o in result["orders"])
    mock_route.assert_not_called()


def test_run_daily_rebalance_live_submits_and_logs_trade():
    from src.execution.daily_trader import run_daily_rebalance
    account = {"equity": 100000.0, "cash": 100000.0}
    target_weights = {"AAPL": 0.20}
    orders = [{"ticker": "AAPL", "side": "buy", "qty": 50, "reason": "rebalance drift=+0.20"}]
    fill = {"order_id": "abc123", "fill_price": 201.0, "side": "buy", "qty": 50, "ticker": "AAPL"}

    with patch("src.execution.daily_trader.is_paused", return_value=False), \
         patch("src.execution.daily_trader.get_account", return_value=account), \
         _passing_gates(), \
         patch("src.execution.daily_trader._today_target_weights", return_value=(target_weights, "Bull/Low-Vol")), \
         patch("src.execution.daily_trader.get_positions", return_value=[]), \
         patch("src.execution.daily_trader.get_latest_price", return_value=200.0), \
         patch("src.execution.daily_trader.compute_portfolio_correlation", return_value=0.0), \
         patch("src.execution.daily_trader._get_vol_60d", return_value=0.15), \
         patch("src.execution.daily_trader.compute_max_shares", return_value=1000), \
         patch("src.execution.daily_trader.compute_rebalance_orders", return_value=orders), \
         patch("src.execution.daily_trader.check_position_limit", return_value=True), \
         patch("src.execution.daily_trader.log_decision", return_value=1), \
         patch("src.execution.daily_trader.route_order", return_value=fill), \
         patch("src.execution.daily_trader.log_trade", return_value="trade-xyz") as mock_log_trade:
        result = run_daily_rebalance(dry_run=False)

    assert result["status"] == "ok"
    assert result["orders"][0]["submitted"] is True
    assert result["orders"][0]["trade_id"] == "trade-xyz"
    mock_log_trade.assert_called_once()
    call_kwargs = mock_log_trade.call_args.kwargs
    assert call_kwargs["fill_price"] == 201.0
    assert call_kwargs["ticker"] == "AAPL"


def test_run_daily_rebalance_unfilled_order_not_logged_as_trade():
    from src.execution.daily_trader import run_daily_rebalance
    account = {"equity": 100000.0, "cash": 100000.0}
    target_weights = {"AAPL": 0.20}
    orders = [{"ticker": "AAPL", "side": "buy", "qty": 50, "reason": "rebalance drift=+0.20"}]

    with patch("src.execution.daily_trader.is_paused", return_value=False), \
         patch("src.execution.daily_trader.get_account", return_value=account), \
         _passing_gates(), \
         patch("src.execution.daily_trader._today_target_weights", return_value=(target_weights, "Bull/Low-Vol")), \
         patch("src.execution.daily_trader.get_positions", return_value=[]), \
         patch("src.execution.daily_trader.get_latest_price", return_value=200.0), \
         patch("src.execution.daily_trader.compute_portfolio_correlation", return_value=0.0), \
         patch("src.execution.daily_trader._get_vol_60d", return_value=0.15), \
         patch("src.execution.daily_trader.compute_max_shares", return_value=1000), \
         patch("src.execution.daily_trader.compute_rebalance_orders", return_value=orders), \
         patch("src.execution.daily_trader.check_position_limit", return_value=True), \
         patch("src.execution.daily_trader.log_decision", return_value=1), \
         patch("src.execution.daily_trader.route_order", return_value=None), \
         patch("src.execution.daily_trader.log_trade") as mock_log_trade:
        result = run_daily_rebalance(dry_run=False)

    assert result["orders"][0]["submitted"] is False
    assert result["orders"][0]["filled"] is False
    mock_log_trade.assert_not_called()


def test_run_daily_rebalance_skips_ticker_over_position_limit():
    from src.execution.daily_trader import run_daily_rebalance
    account = {"equity": 100000.0, "cash": 100000.0}
    target_weights = {"AAPL": 0.20}
    orders = [{"ticker": "AAPL", "side": "buy", "qty": 50, "reason": "rebalance drift=+0.20"}]

    with patch("src.execution.daily_trader.is_paused", return_value=False), \
         patch("src.execution.daily_trader.get_account", return_value=account), \
         _passing_gates(), \
         patch("src.execution.daily_trader._today_target_weights", return_value=(target_weights, "Bull/Low-Vol")), \
         patch("src.execution.daily_trader.get_positions", return_value=[]), \
         patch("src.execution.daily_trader.get_latest_price", return_value=200.0), \
         patch("src.execution.daily_trader.compute_portfolio_correlation", return_value=0.0), \
         patch("src.execution.daily_trader._get_vol_60d", return_value=0.15), \
         patch("src.execution.daily_trader.compute_max_shares", return_value=1000), \
         patch("src.execution.daily_trader.compute_rebalance_orders", return_value=orders), \
         patch("src.execution.daily_trader.check_position_limit", return_value=False), \
         patch("src.execution.daily_trader.route_order") as mock_route:
        result = run_daily_rebalance(dry_run=False)

    assert result["orders"] == []
    mock_route.assert_not_called()
