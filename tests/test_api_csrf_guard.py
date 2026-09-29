"""The dashboard API must reject cross-site / header-less writes and non-local Host headers."""
from unittest.mock import patch

from fastapi.testclient import TestClient

from dashboard_api.main import app

client = TestClient(app, base_url="http://localhost")
DASHBOARD = {"X-Artemis-Client": "dashboard"}


def test_write_without_client_header_is_rejected():
    with patch("src.execution.daily_trader.run_daily_rebalance") as rebalance:
        resp = client.post("/api/trading/rebalance/execute")
    assert resp.status_code == 403
    rebalance.assert_not_called()


def test_write_from_foreign_origin_is_rejected_even_with_header():
    with patch("src.execution.daily_trader.run_daily_rebalance") as rebalance:
        resp = client.post(
            "/api/trading/rebalance/execute",
            headers={**DASHBOARD, "Origin": "https://evil.example"},
        )
    assert resp.status_code == 403
    rebalance.assert_not_called()


def test_write_from_dashboard_is_allowed():
    with patch("src.execution.daily_trader.run_daily_rebalance", return_value={"status": "ok"}) as rebalance:
        resp = client.post(
            "/api/trading/rebalance/preview",
            headers={**DASHBOARD, "Origin": "http://localhost:5173"},
        )
    assert resp.status_code == 200
    rebalance.assert_called_once_with(dry_run=True)


def test_kill_switch_resume_requires_header():
    resp = client.post("/api/kill-switch/resume")
    assert resp.status_code == 403


def test_reads_do_not_require_header():
    assert client.get("/api/health").status_code == 200


def test_non_local_host_is_rejected():
    rebound = TestClient(app, base_url="http://attacker.example")
    assert rebound.get("/api/health").status_code == 400
