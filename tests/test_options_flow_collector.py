"""Tests for the options_flow collector's pure logic: symbol parsing, volume
metrics, IV rank, and the transaction-rollback-on-failure behavior."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.data.collectors import options_flow_collector as ofc


def _bar(volume):
    return SimpleNamespace(volume=volume)


def test_nearest_expiry_chain_groups_by_expiry_and_picks_earliest():
    client = MagicMock()
    client.get_option_chain.return_value = {
        "AAPL260710C00150000": object(),
        "AAPL260710P00150000": object(),
        "AAPL260703C00150000": object(),  # earlier expiry
    }
    result = ofc._nearest_expiry_chain(client, "AAPL", spot=150.0)
    assert result == ("2026-07-03", ["AAPL260703C00150000"], [])


def test_nearest_expiry_chain_returns_none_when_chain_empty():
    client = MagicMock()
    client.get_option_chain.return_value = {}
    assert ofc._nearest_expiry_chain(client, "AAPL", spot=150.0) is None


def test_volume_metrics_computes_put_call_ratio_and_unusual_volume():
    client = MagicMock()
    client.get_option_bars.return_value.data = {
        "C1": [_bar(10), _bar(10), _bar(50)],  # today=50, trailing avg=10 -> spike
        "P1": [_bar(5), _bar(5), _bar(50)],
    }
    result = ofc._volume_metrics(client, ["C1"], ["P1"])
    assert result["call_volume"] == 50
    assert result["put_volume"] == 50
    assert result["put_call_ratio"] == 1.0
    assert result["unusual_volume"] is True


def test_volume_metrics_clips_extreme_put_call_ratio():
    client = MagicMock()
    client.get_option_bars.return_value.data = {
        "C1": [_bar(1)],
        "P1": [_bar(1_000_000)],
    }
    result = ofc._volume_metrics(client, ["C1"], ["P1"])
    assert result["put_call_ratio"] == 999.0


def test_volume_metrics_none_put_call_ratio_when_no_call_volume():
    client = MagicMock()
    client.get_option_bars.return_value.data = {
        "C1": [_bar(0)],
        "P1": [_bar(5)],
    }
    result = ofc._volume_metrics(client, ["C1"], ["P1"])
    assert result["put_call_ratio"] is None


def test_volume_metrics_returns_none_for_empty_symbols():
    assert ofc._volume_metrics(MagicMock(), [], []) is None


def test_iv_rank_returns_none_with_insufficient_history():
    cur = MagicMock()
    cur.fetchall.return_value = [("0.20",), ("0.25",)]  # only 2 prior days
    assert ofc._iv_rank(cur, "AAPL", atm_iv=0.30) == (None, None)


def test_iv_rank_computes_percentile_with_enough_history():
    cur = MagicMock()
    cur.fetchall.return_value = [("0.10",), ("0.20",), ("0.30",), ("0.40",), ("0.50",)]
    rank, percentile = ofc._iv_rank(cur, "AAPL", atm_iv=0.60)
    assert rank == 100.0  # highest of all 6 values
    assert rank == percentile


def test_spot_price_falls_back_to_yfinance_when_quote_stale():
    stale_quote = {"price": 100.0, "age_seconds": 99999.0}
    with patch("src.execution.broker.get_latest_quote", return_value=stale_quote), \
         patch("yfinance.Ticker") as mock_ticker:
        import pandas as pd
        mock_ticker.return_value.history.return_value = pd.DataFrame({"Close": [372.97]})
        assert ofc._spot_price("MSFT") == 372.97


def test_spot_price_uses_fresh_alpaca_quote():
    fresh_quote = {"price": 186.98, "age_seconds": 5.0}
    with patch("src.execution.broker.get_latest_quote", return_value=fresh_quote):
        assert ofc._spot_price("MSFT") == 186.98


def test_collect_rolls_back_after_per_ticker_failure_so_next_ticker_succeeds():
    """A DB error on one ticker must not poison the transaction for the rest."""
    with patch.object(ofc, "_option_client", return_value=MagicMock()), \
         patch.object(ofc, "_spot_price", side_effect=[100.0, 200.0]), \
         patch.object(ofc, "_nearest_expiry_chain", return_value=("2026-07-10", ["C1"], ["P1"])), \
         patch.object(ofc, "_volume_metrics", return_value={
             "call_volume": 10, "put_volume": 10, "put_call_ratio": 1.0, "unusual_volume": False,
         }), \
         patch.object(ofc, "_atm_iv", return_value=0.25), \
         patch.object(ofc, "_iv_rank", return_value=(None, None)), \
         patch.object(ofc, "conn") as mock_conn:
        mock_cursor = MagicMock()
        # First INSERT raises, second succeeds.
        mock_cursor.execute.side_effect = [Exception("boom"), None]
        mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cursor
        mock_c = mock_conn.return_value.__enter__.return_value

        result = ofc.collect(tickers=["BAD", "OK"])

    assert result == {"tickers": 2, "inserted": 1, "skipped": 0, "failed": 1}
    mock_c.rollback.assert_called_once()
