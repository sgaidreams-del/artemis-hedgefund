"""scan_earnings_signals() must never execute orders — only execute_straddle does."""
from datetime import date, timedelta
from unittest.mock import patch

from src.strategy import earnings_options as eo_mod


def test_scan_never_calls_execute_straddle():
    upcoming = [{"ticker": "AAPL", "earnings_date": date.today() + timedelta(days=10), "days_out": 10}]
    signal = {"action": "straddle", "reason": "iv_rank=20.0 < 50", "iv_rank": 20.0, "days_to_earnings": 10}

    with patch.object(eo_mod, "upcoming_earnings", return_value=upcoming), \
         patch.object(eo_mod, "pre_earnings_straddle_signal", return_value=signal), \
         patch.object(eo_mod, "execute_straddle") as mock_execute:
        result = eo_mod.scan_earnings_signals()

    assert len(result) == 1
    assert result[0]["ticker"] == "AAPL"
    assert result[0]["signal"]["action"] == "straddle"
    mock_execute.assert_not_called()


def test_scan_reports_skip_signals_without_executing():
    upcoming = [{"ticker": "MSFT", "earnings_date": date.today() + timedelta(days=10), "days_out": 10}]
    signal = {"action": "skip", "reason": "iv_rank=60.0 >= 50", "iv_rank": 60.0, "days_to_earnings": 10}

    with patch.object(eo_mod, "upcoming_earnings", return_value=upcoming), \
         patch.object(eo_mod, "pre_earnings_straddle_signal", return_value=signal), \
         patch.object(eo_mod, "execute_straddle") as mock_execute:
        result = eo_mod.scan_earnings_signals()

    assert result[0]["signal"]["action"] == "skip"
    mock_execute.assert_not_called()


def test_scan_handles_per_ticker_error_without_aborting():
    upcoming = [
        {"ticker": "BAD", "earnings_date": date.today() + timedelta(days=10), "days_out": 10},
        {"ticker": "OK", "earnings_date": date.today() + timedelta(days=10), "days_out": 10},
    ]

    def fake_signal(ticker, earnings_date):
        if ticker == "BAD":
            raise RuntimeError("boom")
        return {"action": "skip", "reason": "ok", "iv_rank": 10.0, "days_to_earnings": 10}

    with patch.object(eo_mod, "upcoming_earnings", return_value=upcoming), \
         patch.object(eo_mod, "pre_earnings_straddle_signal", side_effect=fake_signal):
        result = eo_mod.scan_earnings_signals()

    assert len(result) == 1
    assert result[0]["ticker"] == "OK"
