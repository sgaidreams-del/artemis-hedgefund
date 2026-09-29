"""Unit tests for the trade simulator engine.

All DB calls are patched; tests exercise pure logic only:
- _sim_buy: inserts position + trade, handles add-to-existing average cost
- _sim_sell: closes/reduces position, computes realized P/L correctly
- run_sim_step: disabled → 'disabled', no scores → 'no_scores'
- run_sim_step: buys and sells based on rebalancer output
- reset_sim: deletes all rows and restores starting cash
"""
from datetime import date
from unittest.mock import MagicMock, patch, call

import pytest

import src.simulation.engine as eng


# ── _sim_buy ────────────────────────────────────────────────────────────────

def test_sim_buy_new_position():
    cur = MagicMock()
    eng._sim_buy(cur, "AAPL", 10, 150.0, date(2026, 1, 2), 0.10)
    assert cur.execute.call_count == 2
    # First call: upsert sim_positions
    sql0 = cur.execute.call_args_list[0][0][0]
    assert "sim_positions" in sql0
    # Second call: insert sim_trades
    sql1 = cur.execute.call_args_list[1][0][0]
    assert "sim_trades" in sql1
    assert "buy" in sql1


def test_sim_buy_uses_correct_notional():
    cur = MagicMock()
    eng._sim_buy(cur, "MSFT", 5, 400.0, date(2026, 1, 2), 0.05)
    args = cur.execute.call_args_list[0][0][1]  # positional args to first execute
    # args: (ticker, qty, price, notional, today, today)
    assert args[2] == 400.0     # avg_cost / price
    assert args[3] == 2000.0    # notional = 5 * 400


# ── _sim_sell ───────────────────────────────────────────────────────────────

def test_sim_sell_full_close_deletes_position():
    cur = MagicMock()
    cur.fetchone.return_value = (10, 1500.0)  # qty=10, cost_basis=1500
    pnl = eng._sim_sell(cur, "AAPL", 10, 160.0, date(2026, 1, 3), 150.0, 0.0)
    assert pnl == pytest.approx((160.0 - 150.0) * 10)
    # Should DELETE the position
    delete_calls = [c for c in cur.execute.call_args_list if "DELETE" in str(c)]
    assert len(delete_calls) == 1


def test_sim_sell_partial_reduces_qty():
    cur = MagicMock()
    cur.fetchone.return_value = (10, 1500.0)  # qty=10
    pnl = eng._sim_sell(cur, "AAPL", 4, 160.0, date(2026, 1, 3), 150.0, 0.0)
    assert pnl == pytest.approx((160.0 - 150.0) * 4)
    # Should UPDATE (not delete) the position
    update_calls = [c for c in cur.execute.call_args_list if "UPDATE" in str(c)]
    assert len(update_calls) == 1
    # Remaining qty = 10 - 4 = 6
    update_args = update_calls[0][0][1]
    assert update_args[0] == 6  # new_qty


def test_sim_sell_loss_produces_negative_pnl():
    cur = MagicMock()
    cur.fetchone.return_value = (5, 1000.0)
    pnl = eng._sim_sell(cur, "TSLA", 5, 180.0, date(2026, 1, 3), 200.0, 0.0)
    assert pnl == pytest.approx((180.0 - 200.0) * 5)  # -100
    assert pnl < 0


# ── run_sim_step ────────────────────────────────────────────────────────────

def test_run_sim_step_disabled_returns_early():
    with patch.object(eng, "is_sim_enabled", return_value=False):
        result = eng.run_sim_step()
    assert result == {"status": "disabled"}


def test_run_sim_step_no_scores_returns_early():
    with patch.object(eng, "is_sim_enabled", return_value=True), \
         patch.object(eng, "conn") as mock_conn:
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = []
        mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cur
        result = eng.run_sim_step()
    assert result["status"] == "no_scores"


def test_run_sim_step_buys_on_new_target():
    """Sim should buy a position when ensemble scores a ticker at non-zero weight."""
    today = date(2026, 7, 6)

    with patch.object(eng, "is_sim_enabled", return_value=True), \
         patch.object(eng, "_get_prices", return_value={"AAPL": 200.0}), \
         patch.object(eng, "_get_vol_60d", return_value=0.20), \
         patch("src.risk.correlation.compute_portfolio_correlation", return_value=0.0), \
         patch.object(eng, "_sim_buy") as mock_buy, \
         patch.object(eng, "_sim_sell") as mock_sell, \
         patch.object(eng, "conn") as mock_conn, \
         patch("src.simulation.engine.date") as mock_date:

        mock_date.today.return_value = today

        call_count = [0]

        def fetchall_side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                return [("AAPL", 0.10)]  # ensemble scores
            if call_count[0] == 2:
                return []  # no open positions
            return []

        mock_cur = MagicMock()
        mock_cur.fetchall.side_effect = fetchall_side_effect
        mock_cur.fetchone.side_effect = [
            (100_000.0, 100_000.0),  # _get_sim_state: cash, starting_capital
            None,                     # sim_snapshots peak
            None,                     # sim_snapshots prev
        ]
        c = mock_conn.return_value.__enter__.return_value
        c.cursor.return_value.__enter__.return_value = mock_cur

        result = eng.run_sim_step()

    assert result["status"] == "ok"
    assert mock_buy.called
    assert not mock_sell.called


# ── reset_sim ────────────────────────────────────────────────────────────────

def test_reset_sim_deletes_tables_and_restores_cash():
    with patch.object(eng, "conn") as mock_conn:
        mock_cur = MagicMock()
        c = mock_conn.return_value.__enter__.return_value
        c.cursor.return_value.__enter__.return_value = mock_cur

        result = eng.reset_sim()

    assert result["status"] == "reset"
    assert result["starting_capital"] == 100_000.0
    # Verify DELETE calls were issued
    executed_sqls = [str(c[0][0]) for c in mock_cur.execute.call_args_list]
    assert any("DELETE FROM sim_weekly_reports" in s for s in executed_sqls)
    assert any("DELETE FROM sim_positions" in s for s in executed_sqls)
    assert any("UPDATE sim_config" in s for s in executed_sqls)
