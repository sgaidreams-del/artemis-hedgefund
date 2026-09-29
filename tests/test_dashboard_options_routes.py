"""Dashboard /api/options endpoints: hedge-review, earnings-scan, earnings-scan/execute."""
from unittest.mock import patch

from fastapi.testclient import TestClient

from dashboard_api.main import app

client = TestClient(app, base_url="http://localhost", headers={"X-Artemis-Client": "dashboard"})


def test_hedge_review_returns_advisory_data():
    with patch("src.execution.broker.get_account", return_value={"equity": 50_000.0}), \
         patch("src.execution.broker.get_positions", return_value=[]):
        resp = client.get("/api/options/hedge-review")

    assert resp.status_code == 200
    body = resp.json()
    assert body["portfolio_value"] == 50_000.0
    assert body["tail_hedge"]["action"] == "no_hedge"


def test_earnings_scan_is_read_only():
    fake_signals = [{"ticker": "AAPL", "earnings_date": "2026-07-01",
                      "signal": {"action": "skip", "reason": "ok", "iv_rank": 10.0, "days_to_earnings": 10}}]
    with patch("src.strategy.earnings_options.scan_earnings_signals", return_value=fake_signals):
        resp = client.get("/api/options/earnings-scan")

    assert resp.status_code == 200
    assert resp.json()["signals"] == fake_signals


def test_earnings_scan_execute_requires_ticker_and_date():
    resp = client.post("/api/options/earnings-scan/execute", json={"ticker": "AAPL"})
    assert resp.status_code == 422  # missing earnings_date, pydantic validation


def test_earnings_scan_execute_calls_execute_straddle_with_real_portfolio_value():
    fake_result = {"call_order": {"id": "1"}, "put_order": {"id": "2"}, "total_premium": 120.0}
    with patch("src.execution.broker.get_account", return_value={"equity": 75_000.0}), \
         patch("src.strategy.earnings_options.execute_straddle", return_value=fake_result) as mock_exec:
        resp = client.post(
            "/api/options/earnings-scan/execute",
            json={"ticker": "AAPL", "earnings_date": "2026-07-01"},
        )

    assert resp.status_code == 200
    assert resp.json() == fake_result
    args, kwargs = mock_exec.call_args
    assert args[0] == "AAPL"
    assert args[2] == 75_000.0  # real portfolio value, not a hardcoded placeholder
